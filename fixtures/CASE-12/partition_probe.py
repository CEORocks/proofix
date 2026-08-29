#!/usr/bin/env python3
"""Verify genuine broker loss, under-replication, retained storage, and recovery."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time

NAMESPACE = "proofix-case-12"
TOPIC = "proofix-replicated"
BROKERS = (
    "kafka-0.kafka.proofix-case-12.svc.cluster.local:9092,"
    "kafka-1.kafka.proofix-case-12.svc.cluster.local:9092,"
    "kafka-2.kafka.proofix-case-12.svc.cluster.local:9092"
)


def command(args: list[str], check: bool = True, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result


def kubectl(*args: str, check: bool = True) -> str:
    result = command(["kubectl", *args], check=check)
    return result.stdout + (result.stderr if not check else "")


def rpk(*args: str, check: bool = True) -> str:
    return kubectl(
        "exec", "-n", NAMESPACE, "kafka-0", "--", "rpk", *args,
        "-X", f"brokers={BROKERS}", check=check,
    )


def health() -> dict[str, object]:
    raw = rpk("cluster", "health", check=False)
    under = re.search(r"Under-replicated partitions \((\d+)\)", raw)
    down = re.search(r"Nodes down:\s*\[([^]]*)\]", raw)
    healthy = re.search(r"Healthy:\s*(true|false)", raw, re.IGNORECASE)
    if not under or not down or not healthy:
        raise RuntimeError(f"unable to parse cluster health evidence:\n{raw}")
    nodes = [item for item in down.group(1).split() if item]
    return {
        "healthy": healthy.group(1).lower() == "true",
        "under_replicated_partitions": int(under.group(1)),
        "nodes_down": nodes,
        "raw": raw,
    }


def pod_ready() -> bool:
    raw = kubectl("get", "pod/kafka-2", "-n", NAMESPACE, "-o", "json", check=False)
    try:
        payload = json.loads(raw)
        return bool(payload["status"]["containerStatuses"][0]["ready"])
    except (json.JSONDecodeError, KeyError, IndexError, TypeError):
        return False


def pvc_uid() -> str:
    return kubectl("get", "pvc/data-kafka-2", "-n", NAMESPACE, "-o", "jsonpath={.metadata.uid}").strip()


def state() -> dict[str, str]:
    raw = kubectl("get", "configmap/proofix-case12-state", "-n", NAMESPACE, "-o", "json")
    return json.loads(raw).get("data", {})


def topic_evidence() -> dict[str, object]:
    partitions = rpk("topic", "describe", TOPIC, "--print-partitions")
    config = rpk("topic", "describe", TOPIC, "--print-configs")
    rows = []
    for line in partitions.splitlines():
        match = re.match(r"^\s*(\d+)\s+(-?\d+)\s+\d+\s+\[([^]]+)\]", line)
        if match:
            replicas = [item for item in match.group(3).split() if item]
            rows.append({"partition": int(match.group(1)), "leader": int(match.group(2)), "replicas": replicas})
    write_caching_disabled = bool(re.search(r"(?m)^write\.caching\s+false\s+", config))
    return {
        "partition_rows": rows,
        "write_caching_disabled": write_caching_disabled,
        "replication_factor_three": len(rows) == 6 and all(len(row["replicas"]) == 3 for row in rows),
        "partitions_raw": partitions,
        "config_raw": config,
    }


def observe() -> dict[str, object]:
    saved = state()
    current_pvc = pvc_uid()
    override = kubectl(
        "get", "configmap/kafka-startup-override", "-n", NAMESPACE,
        "-o", "jsonpath={.data.extra_args}", check=False,
    ).strip()
    return {
        "cluster": health(),
        "kafka_2_ready": pod_ready(),
        "pvc_uid": current_pvc,
        "saved_pvc_uid": saved.get("pvc_uid", "unset"),
        "pvc_identity_preserved": saved.get("pvc_uid", "unset") in ("unset", current_pvc),
        "startup_override": override,
        "topic": topic_evidence(),
    }


def passed(mode: str, item: dict[str, object]) -> bool:
    cluster = item["cluster"]
    topic = item["topic"]
    common = bool(
        item["pvc_identity_preserved"]
        and topic["write_caching_disabled"]
        and topic["replication_factor_three"]
    )
    if mode == "fault":
        return bool(
            common
            and not item["kafka_2_ready"]
            and item["startup_override"] == "--proofix-invalid-startup-flag"
            and cluster["under_replicated_partitions"] > 0
            and len(cluster["nodes_down"]) >= 1
        )
    return bool(
        common
        and item["kafka_2_ready"]
        and item["startup_override"] == ""
        and cluster["healthy"]
        and cluster["under_replicated_partitions"] == 0
        and not cluster["nodes_down"]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("healthy", "fault", "recovered"))
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    target = "recovered" if args.mode == "healthy" else args.mode
    deadline = time.monotonic() + args.timeout
    latest: dict[str, object] | None = None
    error = ""
    while time.monotonic() < deadline:
        try:
            latest = observe()
            if passed(target, latest):
                break
        except (RuntimeError, subprocess.TimeoutExpired) as exc:
            error = str(exc)
        time.sleep(5)
    ok = latest is not None and passed(target, latest)
    print(json.dumps({"mode": args.mode, "observation": latest, "last_error": error, "passed": ok},
                     indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
