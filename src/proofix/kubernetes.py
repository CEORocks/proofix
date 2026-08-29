"""Bounded Kubernetes tools and real HTTP SLO probes."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import shlex
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping, Sequence, cast

from .types import Action, Observation, SLOSample


@dataclass(frozen=True)
class KubernetesConfig:
    namespace: str
    probe_url: str
    workload_selector: str
    additional_namespaces: tuple[str, ...] = ()
    kubeconfig: str | None = None
    context: str | None = None
    probe_requests: int = 30
    probe_timeout_seconds: float = 2.0
    window_seconds: int = 10
    command_timeout_seconds: int = 30
    command_prefix: tuple[str, ...] = ()


class KubernetesEnvironment:
    """Executes a fixed catalog of diagnostics and reversible mutations."""

    def __init__(self, config: KubernetesConfig) -> None:
        self.config = config

    def observe(self) -> Sequence[Observation]:
        observations = []
        for resource in (
            "pods",
            "deployments",
            "statefulsets",
            "daemonsets",
            "services",
            "endpoints",
            "persistentvolumeclaims",
            "resourcequotas",
            "configmaps",
            "roles",
            "rolebindings",
            "serviceaccounts",
            "secrets",
            "events",
        ):
            observations.append(
                self._observation(
                    f"kubectl/get/{resource}",
                    self._kubectl_json("get", resource, "-n", self.config.namespace),
                )
            )
        observations.append(
            self._observation("kubectl/get/nodes", self._kubectl_json("get", "nodes"))
        )
        for namespace in self.config.additional_namespaces:
            for resource in ("pods", "deployments", "services", "configmaps", "events"):
                observations.append(
                    self._observation(
                        f"kubectl/get/{namespace}/{resource}",
                        self._kubectl_json("get", resource, "-n", namespace),
                    )
                )
        return observations

    def run_test(self, test: Mapping[str, object]) -> Observation:
        kind = str(test.get("kind", ""))
        if kind == "kubectl_get":
            target = self._required_string(test, "target")
            namespace = str(test.get("namespace", self.config.namespace))
            self._assert_namespace(namespace)
            return self._observation(
                f"kubectl/get/{target}",
                self._kubectl_json("get", target, "-n", namespace),
            )
        if kind == "kubectl_describe":
            target = self._required_string(test, "target")
            namespace = str(test.get("namespace", self.config.namespace))
            self._assert_namespace(namespace)
            text = self._kubectl("describe", target, "-n", namespace)
            return self._observation(f"kubectl/describe/{target}", {"text": text})
        if kind == "kubectl_logs":
            pod = self._required_string(test, "pod")
            container = test.get("container")
            command = ["logs", pod, "-n", self.config.namespace, "--tail", "200"]
            if container:
                command.extend(["-c", str(container)])
            text = self._kubectl(*command)
            return self._observation(f"kubectl/logs/{pod}", {"text": text})
        if kind == "kubectl_auth_can_i":
            verb = self._required_string(test, "verb")
            resource = self._required_string(test, "resource")
            command = ["auth", "can-i", verb, resource, "-n", self.config.namespace]
            service_account = test.get("service_account")
            if service_account:
                command.extend(
                    ["--as", f"system:serviceaccount:{self.config.namespace}:{service_account}"]
                )
            answer = self._kubectl(*command).strip()
            return self._observation(
                f"kubectl/auth-can-i/{verb}/{resource}", {"allowed": answer == "yes"}
            )
        if kind == "http_get":
            url = str(test.get("url", self.config.probe_url))
            if url != self.config.probe_url:
                raise ValueError("diagnostic URL is outside the registered SLO probe")
            status, latency = self._http_request(url)
            return self._observation(
                "http/get/probe", {"url": url, "status": status, "latency_ms": latency}
            )
        raise ValueError(f"unsupported discriminating test kind {kind!r}")

    def apply(self, action: Action) -> Observation:
        self._assert_namespace(action.namespace)
        operation = action.operation.lower()
        if operation in {"cordon", "uncordon"}:
            output = self._kubectl(operation, action.target)
        elif operation == "patch":
            patch_value = action.parameters.get("patch")
            if not isinstance(patch_value, Mapping):
                patch_json = action.parameters.get("patch_json")
                if not isinstance(patch_json, str):
                    raise ValueError("patch action requires parameters.patch_json")
                decoded_patch = json.loads(patch_json)
                if not isinstance(decoded_patch, dict):
                    raise ValueError("parameters.patch_json must decode to an object")
                patch_value = decoded_patch
            patch_type = str(action.parameters.get("patch_type", "merge"))
            if patch_type not in {"merge", "strategic", "json"}:
                raise ValueError("unsupported Kubernetes patch type")
            resource, separator, name = action.target.partition("/")
            if not separator or not resource or not name:
                raise ValueError("patch target must use resource/name form")
            output = self._kubectl(
                "patch",
                resource,
                name,
                "-n",
                action.namespace,
                "--type",
                patch_type,
                "-p",
                json.dumps(dict(patch_value), separators=(",", ":")),
            )
            if resource in {"deployment", "deployments", "deployment.apps", "deployments.apps"}:
                output += self._kubectl(
                    "rollout",
                    "status",
                    f"deployment/{name}",
                    "-n",
                    action.namespace,
                    "--timeout=180s",
                )
        elif operation == "rollout_restart":
            output = self._kubectl("rollout", "restart", action.target, "-n", action.namespace)
            if action.target.startswith(("deployment/", "deployments/")):
                output += self._kubectl(
                    "rollout",
                    "status",
                    action.target,
                    "-n",
                    action.namespace,
                    "--timeout=180s",
                )
        elif operation == "scale":
            replicas = int(action.parameters["replicas"])
            if not 0 <= replicas <= 100:
                raise ValueError("replica count is outside the safety bound")
            output = self._kubectl(
                "scale", action.target, "-n", action.namespace, f"--replicas={replicas}"
            )
        elif operation == "delete_pod":
            if not action.target.startswith(("pod/", "pods/")):
                raise ValueError("delete_pod can target only an individual pod")
            output = self._kubectl("delete", action.target, "-n", action.namespace)
        elif operation == "sync_secret_and_rollout":
            output = self._sync_secret_and_rollout(action)
        elif operation == "replace_unbound_pvc":
            output = self._replace_unbound_pvc(action)
        else:
            raise ValueError(f"environment cannot execute operation {operation!r}")
        return self._observation(
            f"kubectl/{operation}/{action.target}", {"stdout": output, "changed": True}
        )

    def _sync_secret_and_rollout(self, action: Action) -> str:
        resource, separator, target_name = action.target.partition("/")
        if not separator or resource not in {"secret", "secrets"} or not target_name:
            raise ValueError("sync_secret_and_rollout target must be secret/name")
        source_name = action.parameters.get("source_secret")
        key = action.parameters.get("key") or "password"
        deployment = action.parameters.get("deployment")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError("sync_secret_and_rollout requires source_secret")
        if not isinstance(key, str) or not key:
            raise ValueError("sync_secret_and_rollout requires key")
        if not isinstance(deployment, str) or not deployment:
            raise ValueError("sync_secret_and_rollout requires deployment")
        encoded = self._kubectl(
            "get",
            "secret",
            source_name,
            "-n",
            action.namespace,
            "-o",
            f"jsonpath={{.data.{key}}}",
        ).strip()
        if not encoded:
            raise ValueError(f"source Secret has no {key!r} key")
        digest = hashlib.sha256(base64.b64decode(encoded)).hexdigest()
        self._kubectl(
            "patch",
            "secret",
            target_name,
            "-n",
            action.namespace,
            "--type",
            "merge",
            "-p",
            json.dumps({"data": {key: encoded}}, separators=(",", ":")),
        )
        version = self._kubectl(
            "get",
            "secret",
            target_name,
            "-n",
            action.namespace,
            "-o",
            "jsonpath={.metadata.resourceVersion}",
        ).strip()
        self._kubectl(
            "patch",
            "deployment",
            deployment,
            "-n",
            action.namespace,
            "--type",
            "merge",
            "-p",
            json.dumps(
                {
                    "spec": {
                        "template": {
                            "metadata": {
                                "annotations": {
                                    "proofix.io/billing-secret-resource-version": version
                                }
                            }
                        }
                    }
                },
                separators=(",", ":"),
            ),
        )
        self._kubectl(
            "rollout",
            "status",
            f"deployment/{deployment}",
            "-n",
            action.namespace,
            "--timeout=180s",
        )
        return f"Secret key synchronized by digest {digest}; deployment rolled out"

    def _replace_unbound_pvc(self, action: Action) -> str:
        resource, separator, name = action.target.partition("/")
        if not separator or resource not in {"pvc", "persistentvolumeclaim"} or not name:
            raise ValueError("replace_unbound_pvc target must be pvc/name")
        current = self._raw_kubectl_json(
            "get", "pvc", name, "-n", action.namespace
        )
        metadata = current.get("metadata", {})
        spec = current.get("spec", {})
        status = current.get("status", {})
        if not all(isinstance(value, Mapping) for value in (metadata, spec, status)):
            raise RuntimeError("PVC response is malformed")
        labels = metadata.get("labels", {})
        if not isinstance(labels, Mapping):
            labels = {}
        safe = (
            status.get("phase") == "Pending"
            and not spec.get("volumeName")
            and labels.get("proofix.io/benchmark-owned") == "true"
            and labels.get("proofix.io/expected-empty") == "true"
        )
        if not safe:
            raise ValueError("PVC is not evaluator-confirmed Pending/unbound/empty/owned")
        mounted = self._raw_kubectl_json("get", "pods", "-n", action.namespace)
        for pod in mounted.get("items", []):
            if not isinstance(pod, Mapping):
                continue
            pod_status = pod.get("status", {})
            pod_spec = pod.get("spec", {})
            if not isinstance(pod_status, Mapping) or not isinstance(pod_spec, Mapping):
                continue
            if pod_status.get("phase") != "Running":
                continue
            for volume in pod_spec.get("volumes", []):
                if isinstance(volume, Mapping):
                    claim = volume.get("persistentVolumeClaim", {})
                    if isinstance(claim, Mapping) and claim.get("claimName") == name:
                        raise ValueError("PVC is mounted by a Running pod")
        storage_class = action.parameters.get("storage_class")
        size = action.parameters.get("size") or "64Mi"
        if not isinstance(storage_class, str) or not storage_class:
            raise ValueError("replace_unbound_pvc requires storage_class")
        if not isinstance(size, str) or not size:
            raise ValueError("replace_unbound_pvc requires size")
        self._kubectl("delete", "pvc", name, "-n", action.namespace, "--wait=true")
        manifest = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": name, "namespace": action.namespace, "labels": dict(labels)},
            "spec": {
                "accessModes": list(spec.get("accessModes", ["ReadWriteOnce"])),
                "storageClassName": storage_class,
                "resources": {"requests": {"storage": size}},
            },
        }
        self._kubectl_input(
            json.dumps(manifest), "apply", "-f", "-"
        )
        return f"recreated evaluator-confirmed empty PVC with StorageClass {storage_class}"

    def rollback(self, action: Action) -> Observation:
        if action.rollback is None:
            raise ValueError("rollback specification is missing")
        rollback = dict(action.rollback)
        operation = str(rollback.get("operation", action.operation))
        parameters = rollback.get("parameters", rollback)
        if not isinstance(parameters, Mapping):
            raise ValueError("rollback parameters must be an object")
        inverse = Action(
            operation=operation,
            target=str(rollback.get("target", action.target)),
            namespace=str(rollback.get("namespace", action.namespace)),
            parameters=cast(Mapping[str, Any], parameters),
            reversible=False,
            rollback=None,
        )
        result = self.apply(inverse)
        return self._observation(
            f"kubectl/rollback/{action.target}",
            {"inverse": inverse.to_dict(), "result": result.to_dict()},
        )

    def probe_slo(self) -> SLOSample:
        latencies: list[float] = []
        errors = 0
        for _ in range(self.config.probe_requests):
            status, latency_ms = self._http_request(self.config.probe_url)
            latencies.append(latency_ms)
            if status >= 500 or status == 0:
                errors += 1
            if self.config.window_seconds > 0:
                time.sleep(self.config.window_seconds / self.config.probe_requests)
        pods_ready = self._workload_ready()
        sorted_latencies = sorted(latencies)
        rank = max(0, math.ceil(0.95 * len(sorted_latencies)) - 1)
        return SLOSample(
            error_rate=errors / len(latencies),
            p95_latency_ms=sorted_latencies[rank],
            healthy=pods_ready,
            source=self._source(
                "slo/http-and-pods",
                {
                    "requests": len(latencies),
                    "errors": errors,
                    "p95_latency_ms": sorted_latencies[rank],
                    "pods_ready": pods_ready,
                },
            ),
            window_seconds=self.config.window_seconds,
        )

    def _workload_ready(self) -> bool:
        payload = self._kubectl_json(
            "get",
            "pods",
            "-n",
            self.config.namespace,
            "-l",
            self.config.workload_selector,
        )
        items = payload.get("items", [])
        if not isinstance(items, list) or not items:
            return False
        for pod in items:
            if not isinstance(pod, Mapping):
                return False
            status = pod.get("status", {})
            if not isinstance(status, Mapping) or status.get("phase") != "Running":
                return False
            conditions = status.get("conditions", [])
            ready = any(
                isinstance(item, Mapping)
                and item.get("type") == "Ready"
                and item.get("status") == "True"
                for item in conditions if isinstance(conditions, list)
            )
            if not ready:
                return False
        return True

    def _http_request(self, url: str) -> tuple[int, float]:
        started = time.monotonic()
        try:
            with urllib.request.urlopen(url, timeout=self.config.probe_timeout_seconds) as response:
                response.read(1024)
                status = int(response.status)
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
        except (urllib.error.URLError, TimeoutError):
            status = 0
        return status, (time.monotonic() - started) * 1000.0

    def _kubectl_json(self, *arguments: str) -> dict[str, Any]:
        value = self._raw_kubectl_json(*arguments)
        _redact_secrets(value)
        return cast(dict[str, Any], _sanitize_kubernetes(value))

    def _raw_kubectl_json(self, *arguments: str) -> dict[str, Any]:
        text = self._kubectl(*arguments, "-o", "json")
        value = json.loads(text)
        if not isinstance(value, dict):
            raise RuntimeError("kubectl returned a non-object JSON document")
        return cast(dict[str, Any], value)

    def _kubectl(self, *arguments: str) -> str:
        kubectl_command = ["kubectl"]
        if self.config.kubeconfig:
            kubectl_command.extend(["--kubeconfig", self.config.kubeconfig])
        if self.config.context:
            kubectl_command.extend(["--context", self.config.context])
        kubectl_command.extend(arguments)
        command = (
            [*self.config.command_prefix, shlex.join(kubectl_command)]
            if self.config.command_prefix
            else kubectl_command
        )
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=self.config.command_timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"kubectl command failed ({completed.returncode}): {completed.stderr[-2000:].strip()}"
            )
        return completed.stdout[:200_000]

    def _kubectl_input(self, input_text: str, *arguments: str) -> str:
        kubectl_command = ["kubectl"]
        if self.config.kubeconfig:
            kubectl_command.extend(["--kubeconfig", self.config.kubeconfig])
        if self.config.context:
            kubectl_command.extend(["--context", self.config.context])
        kubectl_command.extend(arguments)
        command = (
            [*self.config.command_prefix, shlex.join(kubectl_command)]
            if self.config.command_prefix
            else kubectl_command
        )
        completed = subprocess.run(
            command,
            input=input_text,
            text=True,
            capture_output=True,
            timeout=self.config.command_timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"kubectl command failed ({completed.returncode}): {completed.stderr[-2000:].strip()}"
            )
        return completed.stdout[:200_000]

    def _observation(self, prefix: str, data: Mapping[str, Any]) -> Observation:
        return Observation(source=self._source(prefix, data), data=dict(data))

    @staticmethod
    def _source(prefix: str, data: Mapping[str, Any]) -> str:
        digest = hashlib.sha256(
            json.dumps(dict(data), sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
        return f"{prefix}#{digest}"

    def _assert_namespace(self, namespace: str) -> None:
        allowed = {self.config.namespace, *self.config.additional_namespaces}
        if namespace not in allowed:
            raise ValueError(f"namespace {namespace!r} is outside the registered environment")

    @staticmethod
    def _required_string(value: Mapping[str, object], key: str) -> str:
        result = value.get(key)
        if not isinstance(result, str) or not result:
            raise ValueError(f"test requires a non-empty {key!r}")
        return result


def _sanitize_kubernetes(value: object) -> object:
    """Remove high-volume server metadata while retaining diagnostic state."""
    if isinstance(value, list):
        return [_sanitize_kubernetes(item) for item in value]
    if not isinstance(value, dict):
        return value
    cleaned: dict[str, object] = {}
    for key, item in value.items():
        if key in {"managedFields", "resourceVersion", "uid", "selfLink"}:
            continue
        if key == "annotations" and isinstance(item, dict):
            annotations = {
                annotation: annotation_value
                for annotation, annotation_value in item.items()
                if annotation != "kubectl.kubernetes.io/last-applied-configuration"
            }
            cleaned[key] = _sanitize_kubernetes(annotations)
            continue
        cleaned[str(key)] = _sanitize_kubernetes(item)
    return cleaned


def _redact_secrets(value: dict[str, Any]) -> None:
    """Replace Secret bytes with comparison-safe hashes before tracing."""
    candidates: list[dict[str, Any]] = []
    if value.get("kind") == "Secret":
        candidates.append(value)
    items = value.get("items")
    if isinstance(items, list):
        candidates.extend(
            item for item in items
            if isinstance(item, dict) and item.get("kind") == "Secret"
        )
    for secret in candidates:
        metadata = secret.get("metadata")
        if isinstance(metadata, dict) and "resourceVersion" in metadata:
            metadata["proofixResourceVersion"] = metadata["resourceVersion"]
        data = secret.get("data")
        redacted: dict[str, dict[str, object]] = {}
        if isinstance(data, dict):
            for key, encoded in data.items():
                if not isinstance(encoded, str):
                    continue
                decoded = base64.b64decode(encoded)
                redacted[str(key)] = {
                    "sha256": hashlib.sha256(decoded).hexdigest(),
                    "bytes": len(decoded),
                }
        secret["data"] = redacted
        secret.pop("stringData", None)
