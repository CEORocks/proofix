#!/usr/bin/env python3
"""Fault checks and strict three-window HTTP SLO verification for CASE-10."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request


def request(url: str, timeout: float) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except (OSError, TimeoutError):
        status = 0
    return status, (time.perf_counter() - started) * 1000.0


def p95(values: list[float]) -> float:
    return sorted(values)[max(0, math.ceil(0.95 * len(values)) - 1)]


def fault(base_url: str, timeout: float) -> int:
    statuses = [request(f"{base_url}/billing?fault={index}", timeout)[0]
                for index in range(10)]
    passed = statuses and all(status == 503 for status in statuses)
    print(json.dumps({"mode": "fault", "statuses": statuses, "passed": passed}))
    return 0 if passed else 1


def slo(base_url: str, requests: int, timeout: float) -> int:
    windows = []
    for window in range(1, 4):
        results = [request(f"{base_url}/billing?window={window}&request={index}", timeout)
                   for index in range(requests)]
        statuses = [status for status, _ in results]
        failures = sum(status != 200 for status in statuses)
        errors = sum(500 <= status <= 599 for status in statuses)
        latency = p95([elapsed for _, elapsed in results])
        rate = errors / requests
        passed = failures == 0 and rate < 0.001 and latency < 200.0
        windows.append({"window": window, "requests": requests, "failures": failures,
                        "http_5xx": errors, "http_5xx_rate": rate,
                        "p95_latency_ms": latency, "passed": passed})
    payload = {"mode": "slo", "thresholds": {"http_5xx_rate_lt": 0.001,
               "p95_latency_ms_lt": 200.0, "consecutive_windows": 3},
               "windows": windows, "passed": len(windows) == 3 and
               all(window["passed"] for window in windows)}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("fault", "slo"))
    parser.add_argument("--base-url", default="http://127.0.0.1:30080")
    parser.add_argument("--requests", type=int, default=250)
    parser.add_argument("--timeout", type=float, default=2.0)
    args = parser.parse_args()
    if args.mode == "fault":
        return fault(args.base_url.rstrip("/"), args.timeout)
    return slo(args.base_url.rstrip("/"), args.requests, args.timeout)


if __name__ == "__main__":
    sys.exit(main())
