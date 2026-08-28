"""One-run live benchmark harness with isolated fixture lifecycle."""

from __future__ import annotations

import hashlib
import json
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
    artifact_root: str = "artifacts/runs"
    model: str = "gpt-5.6-sol"
    kubeconfig: str = "/etc/rancher/k3s/k3s.yaml"
    probe_path: str = "/"
    probe_requests: int = 1000
    window_seconds: int = 10
    verification_settle_seconds: float = 5.0
    max_model_calls: int = 5


class FixtureController:
    def __init__(self, *, host: str, fixture_dir: str, kubeconfig: str) -> None:
        self.host = host
        self.fixture_dir = fixture_dir.rstrip("/")
        self.kubeconfig = kubeconfig

    def run(self, script: str, *, timeout_seconds: int = 600) -> str:
        if script not in {"install.sh", "inject.sh", "reset.sh", "verify.sh"}:
            raise ValueError("fixture script is not allowlisted")
        remote = shlex.join(
            [
                "env",
                f"KUBECONFIG={self.kubeconfig}",
                f"{self.fixture_dir}/{script}",
            ]
        )
        completed = subprocess.run(
            ["ssh", self.host, remote],
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
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
    )
    lifecycle: dict[str, str] = {}
    started = time.monotonic()
    try:
        lifecycle["install"] = fixture.run("install.sh")
        lifecycle["reset"] = fixture.run("reset.sh")
        if not bool(case["control"]):
            lifecycle["inject"] = fixture.run("inject.sh")
        (run_dir / "fixture.json").write_text(
            json.dumps(lifecycle, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with SSHTunnel(
            host=config.host,
            local_port=config.local_port,
            remote_port=config.node_port,
        ):
            environment = KubernetesEnvironment(
                KubernetesConfig(
                    namespace=config.namespace,
                    probe_url=f"http://127.0.0.1:{config.local_port}{config.probe_path}",
                    workload_selector=config.workload_selector,
                    kubeconfig=config.kubeconfig,
                    command_prefix=("ssh", config.host),
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
            policy = SafetyPolicy(allowed_namespaces=[config.namespace], max_actions=20)
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
            vrs = evaluate_vrs(outcome, expect_abstention=bool(case["control"]))
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
