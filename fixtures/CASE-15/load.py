#!/usr/bin/env python3
from __future__ import annotations

import argparse, json, math, sys, time, urllib.error, urllib.request

THRESHOLDS = {"http_5xx_rate_lt": 0.001, "p95_latency_ms_lt": 200.0, "consecutive_windows": 3}

def one(url: str) -> tuple[int, float]:
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(url, timeout=1.0) as response:
            response.read(); status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
    except OSError:
        status = 0
    return status, (time.perf_counter() - started) * 1000

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--base-url", default="http://127.0.0.1:30115")
    parser.add_argument("--requests", type=int, default=100); args = parser.parse_args()
    windows = []
    for window in range(1, 4):
        samples = [one(f"{args.base_url.rstrip('/')}/healthz?w={window}&n={n}") for n in range(args.requests)]
        statuses, latencies = zip(*samples); ordered = sorted(latencies)
        errors = sum(status != 200 for status in statuses); fives = sum(500 <= status < 600 for status in statuses)
        p95 = ordered[max(0, math.ceil(.95 * len(ordered)) - 1)]; rate = fives / len(statuses)
        windows.append({"window": window, "requests": len(statuses), "failures": errors,
                        "http_5xx_rate": rate, "p95_latency_ms": p95,
                        "passed": errors == 0 and rate < 0.001 and p95 < 200.0})
    result = {"thresholds": THRESHOLDS, "windows": windows,
              "passed": len(windows) == 3 and all(w["passed"] for w in windows)}
    print(json.dumps(result, indent=2, sort_keys=True)); return 0 if result["passed"] else 1

if __name__ == "__main__":
    sys.exit(main())
