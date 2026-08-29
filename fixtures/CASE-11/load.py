#!/usr/bin/env python3
"""Strict three-window HTTP SLO verifier for the recovered consumer service."""

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
    return status, (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:30081")
    parser.add_argument("--requests", type=int, default=250)
    parser.add_argument("--timeout", type=float, default=1.0)
    args = parser.parse_args()
    windows = []
    for window in range(1, 4):
        values = [request(args.base_url.rstrip("/") + "/healthz", args.timeout) for _ in range(args.requests)]
        statuses = [status for status, _ in values]
        latencies = sorted(latency for _, latency in values)
        p95 = latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)]
        fives = sum(500 <= status <= 599 for status in statuses)
        rate = fives / args.requests
        passed = all(status == 200 for status in statuses) and rate < 0.001 and p95 < 200.0
        windows.append({"window": window, "requests": args.requests, "http_5xx": fives,
                        "http_5xx_rate": rate, "p95_latency_ms": p95, "passed": passed})
    payload = {"thresholds": {"http_5xx_rate_lt": 0.001, "p95_latency_ms_lt": 200.0,
                               "consecutive_windows": 3},
               "windows": windows, "passed": len(windows) == 3 and all(w["passed"] for w in windows)}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
