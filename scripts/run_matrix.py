#!/usr/bin/env python3
"""Execute the frozen paired benchmark with one sequential worker per cluster."""

from __future__ import annotations

import argparse
from collections import defaultdict
import fcntl
import json
from pathlib import Path
import random
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from proofix.runner import LiveRunConfig, run_live


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "benchmark" / "environments.json"
RESULTS = ROOT / "artifacts" / "benchmark" / "results.jsonl"
WRITE_LOCK = threading.Lock()


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def sync_fixture(case_id: str, host: str) -> str:
    local = ROOT / "fixtures" / case_id
    if host == "local":
        return str(local)
    remote = f"/tmp/proofix-{case_id.lower().replace('-', '')}"
    subprocess.run(
        ["rsync", "-az", "--delete", f"{local}/", f"{host}:{remote}/"],
        check=True,
    )
    subprocess.run(
        [
            "ssh",
            host,
            f"find {remote} -type f \\( -name '*.sh' -o -name '*.py' \\) -exec chmod +x {{}} +",
        ],
        check=True,
    )
    return remote


def append_result(result: dict[str, Any]) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    with WRITE_LOCK, RESULTS.open("a", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        handle.write(json.dumps(result, sort_keys=True) + "\n")
        handle.flush()
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def completed_keys() -> set[tuple[str, str, int]]:
    if not RESULTS.exists():
        return set()
    completed: set[tuple[str, str, int]] = set()
    for line in RESULTS.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if bool(row.get("valid")):
            completed.add(
                (str(row["case_id"]), str(row["system"]), int(row["trial"]))
            )
    return completed


def run_host(
    host: str,
    cases: list[str],
    registry: dict[str, dict[str, Any]],
    trials: list[int],
    systems: list[str],
    seed: int,
    skip_keys: set[tuple[str, str, int]],
    backend: str,
    model: str | None,
    localize_host: bool,
    kubeconfig_override: str | None,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    execution_host = "local" if localize_host else host
    effective_model = model or (
        "gemini-3.7-flash-medium" if backend == "antigravity" else "gpt-5.6-sol"
    )
    for case_id in cases:
        item = registry[case_id]
        fixture_dir = sync_fixture(case_id, execution_host)
        for trial in trials:
            order = list(systems)
            random.Random(seed + int(case_id[-2:]) * 100 + trial).shuffle(order)
            for system in order:
                if (case_id, system, trial) in skip_keys:
                    continue
                config = LiveRunConfig(
                    case_path=str(ROOT / "benchmark" / "cases" / f"{case_id}.json"),
                    system=system,  # type: ignore[arg-type]
                    trial=trial,
                    host=execution_host,
                    remote_fixture_dir=fixture_dir,
                    namespace=str(item["namespace"]),
                    workload_selector=str(item["selector"]),
                    node_port=int(item["node_port"]),
                    local_port=int(item["local_port"]),
                    additional_namespaces=tuple(item.get("additional_namespaces", [])),
                    fixture_environment=tuple(
                        sorted(dict(item.get("fixture_environment", {})).items())
                    ),
                    service_name=str(item.get("service_name", "")),
                    service_port=int(item.get("service_port", 80)),
                    artifact_root=str(ROOT / "artifacts" / "runs"),
                    backend=backend,  # type: ignore[arg-type]
                    model=effective_model,
                    kubeconfig=kubeconfig_override
                    or str(item.get("kubeconfig", "/etc/rancher/k3s/k3s.yaml")),
                    probe_path=str(item["probe_path"]),
                    probe_requests=1000,
                    window_seconds=10,
                    verification_settle_seconds=float(item["settle_seconds"]),
                    max_model_calls=5,
                )
                result = run_live(config)
                append_result(result)
                results.append(result)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default="all")
    parser.add_argument("--trials", default="1,2,3")
    parser.add_argument("--systems", default="react,proofix")
    parser.add_argument("--hosts", default="all")
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--no-resume", action="store_true")
    parser.add_argument("--backend", choices=("codex", "antigravity"), default="codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--localize-host", action="store_true")
    parser.add_argument("--kubeconfig-override", default=None)
    args = parser.parse_args()

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    selected_cases = sorted(registry) if args.cases == "all" else parse_csv(args.cases)
    selected_hosts = None if args.hosts == "all" else set(parse_csv(args.hosts))
    trials = [int(item) for item in parse_csv(args.trials)]
    systems = parse_csv(args.systems)
    grouped: dict[str, list[str]] = defaultdict(list)
    for case_id in selected_cases:
        host = str(registry[case_id]["host"])
        if selected_hosts is None or host in selected_hosts:
            grouped[host].append(case_id)

    skip_keys = set() if args.no_resume else completed_keys()
    all_results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, len(grouped))) as pool:
        futures = {
            pool.submit(
                run_host,
                host,
                cases,
                registry,
                trials,
                systems,
                args.seed,
                skip_keys,
                args.backend,
                args.model,
                args.localize_host,
                args.kubeconfig_override,
            ): host
            for host, cases in grouped.items()
        }
        for future in as_completed(futures):
            all_results.extend(future.result())

    valid = sum(bool(row.get("valid")) for row in all_results)
    print(json.dumps({"executed": len(all_results), "valid": valid, "results": str(RESULTS)}))
    return 0 if valid == len(all_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
