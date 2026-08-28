#!/usr/bin/env python3
"""Deterministic HTTP load and strict three-window SLO verifier for CASE-07."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class WindowResult:
    window: int
    requests: int
    failures: int
    http_5xx: int
    http_5xx_rate: float
    p95_latency_ms: float
    passed: bool


def request(url: str, timeout: float) -> tuple[int, float]:
    started = time.perf_counter()
    status = 0
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except (OSError, TimeoutError):
        status = 0
    latency_ms = (time.perf_counter() - started) * 1000.0
    return status, latency_ms


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def trigger(base_url: str, requests: int, timeout: float) -> int:
    failures = 0
    for index in range(requests):
        status, _ = request(f"{base_url}/price?fault-sequence={index}", timeout)
        if status != 200:
            failures += 1
            time.sleep(0.2)
    print(json.dumps({"mode": "trigger", "requests": requests, "failures": failures}))
    return 0


def verify_slo(base_url: str, windows: int, requests: int, timeout: float) -> int:
    results: list[WindowResult] = []
    for window in range(1, windows + 1):
        latencies: list[float] = []
        failures = 0
        http_5xx = 0
        for index in range(requests):
            status, latency = request(
                f"{base_url}/price?window={window}&request={index}", timeout
            )
            latencies.append(latency)
            if status != 200:
                failures += 1
            if 500 <= status <= 599:
                http_5xx += 1

        rate = http_5xx / requests
        p95 = percentile_nearest_rank(latencies, 0.95)
        passed = failures == 0 and rate < 0.001 and p95 < 200.0
        results.append(
            WindowResult(window, requests, failures, http_5xx, rate, p95, passed)
        )

    payload = {
        "mode": "slo",
        "thresholds": {
            "http_5xx_rate_lt": 0.001,
            "p95_latency_ms_lt": 200.0,
            "consecutive_windows": 3,
        },
        "windows": [asdict(result) for result in results],
        "passed": len(results) == 3 and all(result.passed for result in results),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("trigger", "slo"))
    parser.add_argument("--base-url", default="http://127.0.0.1:30077")
    parser.add_argument("--requests", type=int)
    parser.add_argument("--timeout", type=float, default=1.0)
    args = parser.parse_args()

    if args.mode == "trigger":
        return trigger(args.base_url.rstrip("/"), args.requests or 80, args.timeout)
    return verify_slo(args.base_url.rstrip("/"), 3, args.requests or 250, args.timeout)


if __name__ == "__main__":
    sys.exit(main())

