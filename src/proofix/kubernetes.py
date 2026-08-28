"""Bounded Kubernetes tools and real HTTP SLO probes."""

from __future__ import annotations

import hashlib
import json
import math
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
    kubeconfig: str | None = None
    context: str | None = None
    probe_requests: int = 30
    probe_timeout_seconds: float = 2.0
    window_seconds: int = 10
    command_timeout_seconds: int = 30


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
                raise ValueError("patch action requires an object in parameters.patch")
            patch_type = str(action.parameters.get("patch_type", "merge"))
            if patch_type not in {"merge", "strategic", "json"}:
                raise ValueError("unsupported Kubernetes patch type")
            output = self._kubectl(
                "patch",
                action.target,
                "-n",
                action.namespace,
                "--type",
                patch_type,
                "-p",
                json.dumps(dict(patch_value), separators=(",", ":")),
            )
        elif operation == "rollout_restart":
            output = self._kubectl("rollout", "restart", action.target, "-n", action.namespace)
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
        else:
            raise ValueError(f"environment cannot execute operation {operation!r}")
        return self._observation(
            f"kubectl/{operation}/{action.target}", {"stdout": output, "changed": True}
        )

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
        text = self._kubectl(*arguments, "-o", "json")
        value = json.loads(text)
        if not isinstance(value, dict):
            raise RuntimeError("kubectl returned a non-object JSON document")
        return cast(dict[str, Any], value)

    def _kubectl(self, *arguments: str) -> str:
        command = ["kubectl"]
        if self.config.kubeconfig:
            command.extend(["--kubeconfig", self.config.kubeconfig])
        if self.config.context:
            command.extend(["--context", self.config.context])
        command.extend(arguments)
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

    def _observation(self, prefix: str, data: Mapping[str, Any]) -> Observation:
        return Observation(source=self._source(prefix, data), data=dict(data))

    @staticmethod
    def _source(prefix: str, data: Mapping[str, Any]) -> str:
        digest = hashlib.sha256(
            json.dumps(dict(data), sort_keys=True, default=str).encode()
        ).hexdigest()[:12]
        return f"{prefix}#{digest}"

    def _assert_namespace(self, namespace: str) -> None:
        if namespace != self.config.namespace:
            raise ValueError(f"namespace {namespace!r} is outside the registered environment")

    @staticmethod
    def _required_string(value: Mapping[str, object], key: str) -> str:
        result = value.get(key)
        if not isinstance(result, str) or not result:
            raise ValueError(f"test requires a non-empty {key!r}")
        return result
