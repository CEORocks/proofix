#!/usr/bin/env python3
"""Measure real Redpanda consumer-group members, assignments, offsets, and lag."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass

NAMESPACE = "proofix-case-11"
POD = "redpanda-0"
BROKERS = "redpanda-0.redpanda.proofix-case-11.svc.cluster.local:9092"
GROUP = "proofix-orders-v1"


@dataclass(frozen=True)
class Sample:
    timestamp: float
    members: int
    total_lag: int
    raw: str


def rpk(*args: str, allow_unhealthy: bool = False) -> str:
    result = subprocess.run(
        ["kubectl", "exec", "-n", NAMESPACE, POD, "--", "rpk", *args, "-X", f"brokers={BROKERS}"],
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode and not allow_unhealthy:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout + (result.stderr if allow_unhealthy else "")


def sample() -> Sample:
    raw = rpk("group", "describe", GROUP)
    members_match = re.search(r"(?m)^MEMBERS\s+(\d+)\s*$", raw)
    lag_match = re.search(r"(?m)^TOTAL-LAG\s+(\d+)\s*$", raw)
    if not members_match or not lag_match:
        raise RuntimeError(f"unable to parse live group evidence:\n{raw}")
    return Sample(time.time(), int(members_match.group(1)), int(lag_match.group(1)), raw)


def fault(samples: int, interval: float, min_growth: int) -> int:
    observed: list[Sample] = []
    for index in range(samples):
        observed.append(sample())
        if index + 1 < samples:
            time.sleep(interval)
    lags = [item.total_lag for item in observed]
    passed = (
        all(item.members == 1 for item in observed)
        and all(later > earlier for earlier, later in zip(lags, lags[1:]))
        and lags[-1] - lags[0] >= min_growth
    )
    print(json.dumps({
        "mode": "fault",
        "samples": [asdict(item) for item in observed],
        "minimum_growth": min_growth,
        "passed": passed,
    }, indent=2, sort_keys=True))
    return 0 if passed else 1


def recovered(timeout: int, bound: int) -> int:
    deadline = time.monotonic() + timeout
    observed: list[Sample] = []
    consecutive = 0
    while time.monotonic() < deadline:
        try:
            current = sample()
        except RuntimeError:
            time.sleep(3)
            continue
        observed.append(current)
        if current.members == 3 and current.total_lag <= bound:
            consecutive += 1
            if consecutive == 3:
                break
        else:
            consecutive = 0
        time.sleep(5)
    passed = consecutive == 3
    print(json.dumps({
        "mode": "recovered",
        "lag_bound": bound,
        "required_consecutive_samples": 3,
        "samples": [asdict(item) for item in observed],
        "passed": passed,
    }, indent=2, sort_keys=True))
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("fault", "recovered"))
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--interval", type=float, default=8.0)
    parser.add_argument("--min-growth", type=int, default=100)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--lag-bound", type=int, default=84)
    args = parser.parse_args()
    if args.mode == "fault":
        return fault(args.samples, args.interval, args.min_growth)
    return recovered(args.timeout, args.lag_bound)


if __name__ == "__main__":
    sys.exit(main())
