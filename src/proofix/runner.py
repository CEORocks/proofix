"""One-run live benchmark harness with isolated fixture lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import socket
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .backends import CodexBackend
from .baseline import ReActBaseline
from .cases import load_case
from .evaluator import evaluate_vrs
from .kubernetes import KubernetesConfig, KubernetesEnvironment
from .policy import SafetyPolicy
from .workflow import ProofFixWorkflow


SystemName = Literal["react", "proofix"]


@dataclass(frozen=True)
class LiveRunConfig:
    case_path: str
    system: SystemName
    trial: int
    host: str
    remote_fixture_dir: str
    namespace: str
    workload_selector: str
    node_port: int
    local_port: int
    additional_namespaces: tuple[str, ...] = ()
    fixture_environment: tuple[tuple[str, str], ...] = ()
    service_name: str = ""
    service_port: int = 80
    artifact_root: str = "artifacts/runs"
    model: str = "gpt-5.6-sol"
    kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"
    probe_path: str = "/"
    probe_requests: int = 1000
    window_seconds: int = 10
    verification_settle_seconds: float = 5.0
    max_model_calls: int = 5


class FixtureController:
    def __init__(
        self,
        *,
        host: str,
        fixture_dir: str,
        kubeconfig: str,
        environment: tuple[tuple[str, str], ...] = (),
    ) -> None:
        self.host = host
        self.fixture_dir = fixture_dir.rstrip("/")
        self.kubeconfig = kubeconfig
        self.environment = environment

    def run(
        self,
        script: str,
        *arguments: str,
        timeout_seconds: int = 600,
    ) -> str:
        if script not in {
            "install.sh",
            "inject.sh",
            "reset.sh",
            "verify.sh",
            "verify-evidence.sh",
        }:
            raise ValueError("fixture script is not allowlisted")
        script_command = [f"{self.fixture_dir}/{script}", *arguments]
        if self.host == "local":
            environment = os.environ.copy()
            environment["KUBECONFIG"] = self.kubeconfig
            environment.update(dict(self.environment))
            command = script_command
        else:
            remote = shlex.join(
                [
                    "env",
                    f"KUBECONFIG={self.kubeconfig}",
                    *(f"{key}={value}" for key, value in self.environment),
                    *script_command,
                ]
            )
            command = ["ssh", self.host, remote]
            environment = None
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
            env=environment,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"fixture {script} failed ({completed.returncode}): "
                f"{completed.stderr[-3000:].strip()}"
            )
        return completed.stdout[-20_000:]


class SSHTunnel:
    def __init__(self, *, host: str, local_port: int, remote_port: int) -> None:
        self.host = host
        self.local_port = local_port
        self.remote_port = remote_port
        self.process: subprocess.Popen[str] | None = None

    def __enter__(self) -> "SSHTunnel":
        self.process = subprocess.Popen(
            [
                "ssh",
                "-o",
                "ExitOnForwardFailure=yes",
                "-N",
                "-L",
                f"{self.local_port}:127.0.0.1:{self.remote_port}",
                self.host,
            ],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise RuntimeError(f"SSH tunnel failed: {stderr[-2000:]}")
            try:
                with socket.create_connection(("127.0.0.1", self.local_port), timeout=0.2):
                    return self
            except OSError:
                time.sleep(0.1)
        self.__exit__(None, None, None)
        raise TimeoutError("SSH tunnel did not become ready")

    def __exit__(self, *_: object) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


class KubernetesPortForward:
    def __init__(
        self,
        *,
        kubeconfig: str,
        namespace: str,
        service_name: str,
        service_port: int,
        local_port: int,
    ) -> None:
        self.kubeconfig = kubeconfig
        self.namespace = namespace
        self.service_name = service_name
        self.service_port = service_port
        self.local_port = local_port
        self.process: subprocess.Popen[str] | None = None

    def __enter__(self) -> "KubernetesPortForward":
        if not self.service_name:
            raise ValueError("local Kubernetes transport requires service_name")
        self.process = subprocess.Popen(
            [
                "kubectl",
                "--kubeconfig",
                self.kubeconfig,
                "-n",
                self.namespace,
                "port-forward",
                f"service/{self.service_name}",
                f"{self.local_port}:{self.service_port}",
                "--address=127.0.0.1",
            ],
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                stderr = self.process.stderr.read() if self.process.stderr else ""
                raise RuntimeError(f"kubectl port-forward failed: {stderr[-2000:]}")
            try:
                with socket.create_connection(("127.0.0.1", self.local_port), timeout=0.2):
                    return self
            except OSError:
                time.sleep(0.2)
        self.__exit__(None, None, None)
        raise TimeoutError("kubectl port-forward did not become ready")

    def __exit__(self, *_: object) -> None:
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)


def run_live(config: LiveRunConfig) -> dict[str, Any]:
    case = load_case(config.case_path)
    case_id = str(case["id"])
    run_id = (
        f"{case_id.lower()}-{config.system}-t{config.trial}-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    )
    run_dir = Path(config.artifact_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "config.json").write_text(
        json.dumps(asdict(config), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    fixture = FixtureController(
        host=config.host,
        fixture_dir=config.remote_fixture_dir,
        kubeconfig=config.kubeconfig,
        environment=config.fixture_environment,
    )
    lifecycle: dict[str, str] = {}
    started = time.monotonic()
    try:
        lifecycle["install"] = fixture.run("install.sh")
        if not bool(case["control"]):
            lifecycle["inject"] = fixture.run("inject.sh")
        (run_dir / "fixture.json").write_text(
            json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        transport = (
            KubernetesPortForward(
                kubeconfig=config.kubeconfig,
                namespace=config.namespace,
                service_name=config.service_name,
                service_port=config.service_port,
                local_port=config.local_port,
            )
            if config.host == "local"
            else SSHTunnel(
                host=config.host,
                local_port=config.local_port,
                remote_port=config.node_port,
            )
        )
        with transport:
            environment = KubernetesEnvironment(
                KubernetesConfig(
                    namespace=config.namespace,
                    probe_url=f"http://127.0.0.1:{config.local_port}{config.probe_path}",
                    workload_selector=config.workload_selector,
                    additional_namespaces=config.additional_namespaces,
                    kubeconfig=config.kubeconfig,
                    command_prefix=("ssh", config.host) if config.host != "local" else (),
                    probe_requests=config.probe_requests,
                    window_seconds=config.window_seconds,
                )
            )
            snapshot = [observation.to_dict() for observation in environment.observe()]
            snapshot_json = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
            snapshot_hash = hashlib.sha256(snapshot_json.encode()).hexdigest()
            (run_dir / "initial-snapshot.json").write_text(
                json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            backend = CodexBackend(model=config.model)
            policy = SafetyPolicy(
                allowed_namespaces=[config.namespace, *config.additional_namespaces],
                max_actions=20,
            )
            if config.system == "proofix":
                outcome = ProofFixWorkflow(
                    backend=backend,
                    environment=environment,
                    policy=policy,
                    trace_path=run_dir / "trajectory.jsonl",
                    run_id=run_id,
                    case_id=case_id,
                    verification_settle_seconds=config.verification_settle_seconds,
                ).run(
                    case, expect_abstention=bool(case["control"])
                )
            else:
                outcome = ReActBaseline(
                    backend=backend,
                    environment=environment,
                    policy=policy,
                    trace_path=run_dir / "trajectory.jsonl",
                    run_id=run_id,
                    case_id=case_id,
                    verification_settle_seconds=config.verification_settle_seconds,
                    max_steps=config.max_model_calls,
                ).run(case, expect_abstention=bool(case["control"]))
            semantic_verified = True
            if not bool(case["control"]):
                try:
                    if case_id == "CASE-01":
                        lifecycle["semantic_verify"] = fixture.run("verify-evidence.sh")
                    else:
                        lifecycle["semantic_verify"] = fixture.run(
                            "verify.sh", "recovered"
                        )
                except Exception as semantic_exc:
                    semantic_verified = False
                    lifecycle["semantic_verify_error"] = (
                        f"{type(semantic_exc).__name__}: {semantic_exc}"
                    )
            vrs = evaluate_vrs(
                outcome,
                expect_abstention=bool(case["control"]),
                semantic_verification=semantic_verified,
            )
        elapsed = time.monotonic() - started
        result = {
            "schema_version": "1.0",
            "valid": True,
            "run_id": run_id,
            "case_id": case_id,
            "system": config.system,
            "trial": config.trial,
            "model": config.model,
            "initial_snapshot_sha256": snapshot_hash,
            "elapsed_seconds": elapsed,
            "outcome": outcome.to_dict(),
            "vrs": vrs.to_dict(),
        }
    except Exception as exc:
        result = {
            "schema_version": "1.0",
            "valid": False,
            "run_id": run_id,
            "case_id": case_id,
            "system": config.system,
            "trial": config.trial,
            "model": config.model,
            "elapsed_seconds": time.monotonic() - started,
            "infrastructure_error": f"{type(exc).__name__}: {exc}",
        }
    finally:
        try:
            lifecycle["final_reset"] = fixture.run("reset.sh")
        except Exception as reset_exc:
            lifecycle["final_reset_error"] = f"{type(reset_exc).__name__}: {reset_exc}"
        (run_dir / "fixture.json").write_text(
            json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    (run_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
