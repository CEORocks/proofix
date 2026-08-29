#!/usr/bin/env python3
"""Fixed-concurrency load and strict SLO verifier for CASE-08."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Window:
    window: int
    requests: int
    failures: int
    http_5xx: int
    http_5xx_rate: float
    p95_latency_ms: float
    passed: bool


def one(url: str, timeout: float) -> tuple[int, float]:
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
    return status, (time.perf_counter() - started) * 1000.0


def batch(base_url: str, count: int, concurrency: int, timeout: float) -> list[tuple[int, float]]:
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one, f"{base_url}/search?request={i}", timeout) for i in range(count)]
        return [future.result() for future in futures]


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def trigger(base_url: str, duration: int, concurrency: int, timeout: float) -> int:
    deadline = time.monotonic() + duration
    requests = failures = 0
    while time.monotonic() < deadline:
        results = batch(base_url, concurrency * 2, concurrency, timeout)
        requests += len(results)
        failures += sum(status != 200 for status, _ in results)
    print(json.dumps({"mode": "trigger", "requests": requests, "failures": failures,
                      "concurrency": concurrency, "duration_seconds": duration}))
    return 0


def verify(base_url: str, requests: int, concurrency: int, timeout: float) -> int:
    windows: list[Window] = []
    for number in range(1, 4):
        results = batch(base_url, requests, concurrency, timeout)
        statuses = [status for status, _ in results]
        latencies = [latency for _, latency in results]
        failures = sum(status != 200 for status in statuses)
        errors = sum(500 <= status <= 599 for status in statuses)
        rate = errors / requests
        latency = p95(latencies)
        passed = failures == 0 and rate < 0.001 and latency < 200.0
        windows.append(Window(number, requests, failures, errors, rate, latency, passed))
    payload = {
        "mode": "slo",
        "load_profile": {"concurrency": concurrency, "requests_per_window": requests},
        "thresholds": {"http_5xx_rate_lt": 0.001, "p95_latency_ms_lt": 200.0,
                       "consecutive_windows": 3},
        "windows": [asdict(window) for window in windows],
        "passed": len(windows) == 3 and all(window.passed for window in windows),
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("trigger", "slo"))
    parser.add_argument("--base-url", default="http://127.0.0.1:30078")
    parser.add_argument("--requests", type=int, default=256)
    parser.add_argument("--concurrency", type=int, default=32)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--timeout", type=float, default=3.0)
    args = parser.parse_args()
    if args.mode == "trigger":
        return trigger(args.base_url.rstrip("/"), args.duration, args.concurrency, args.timeout)
    return verify(args.base_url.rstrip("/"), args.requests, args.concurrency, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
