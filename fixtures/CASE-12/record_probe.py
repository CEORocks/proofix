#!/usr/bin/env python3
"""Prove that all current-run acknowledged marker records remain readable."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys

NAMESPACE = "proofix-case-12"
TOPIC = "proofix-replicated"
BROKERS = (
    "kafka-0.kafka.proofix-case-12.svc.cluster.local:9092,"
    "kafka-1.kafka.proofix-case-12.svc.cluster.local:9092,"
    "kafka-2.kafka.proofix-case-12.svc.cluster.local:9092"
)


def main() -> int:
    state_result = subprocess.run(
        ["kubectl", "get", "configmap/proofix-case12-state", "-n", NAMESPACE, "-o", "json"],
        text=True, capture_output=True, check=False, timeout=30,
    )
    if state_result.returncode:
        print(state_result.stderr, file=sys.stderr)
        return 2
    state = json.loads(state_result.stdout).get("data", {})
    count = int(state.get("marker_count", "60"))
    prefixes = [state.get("pre_prefix", "unset"), state.get("fault_prefix", "unset")]
    if "unset" in prefixes:
        print("no current CASE-12 marker run has been injected", file=sys.stderr)
        return 2
    expected = {f"{prefix}-{index:04d}" for prefix in prefixes for index in range(count)}
    result = subprocess.run(
        ["kubectl", "exec", "-n", NAMESPACE, "kafka-0", "--", "rpk", "topic", "consume", TOPIC,
         "--offset", ":end", "--format", "%v\\n", "-X", f"brokers={BROKERS}"],
        text=True, capture_output=True, check=False, timeout=180,
    )
    observed = set(result.stdout.splitlines())
    missing = sorted(expected - observed)
    digest = hashlib.sha256("\n".join(sorted(expected)).encode()).hexdigest()
    payload = {
        "expected_records": len(expected),
        "observed_matching_records": len(expected & observed),
        "missing": missing,
        "expected_sha256": digest,
        "consumer_exit_code": result.returncode,
        "passed": result.returncode == 0 and not missing,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
