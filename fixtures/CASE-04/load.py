#!/usr/bin/env python3
"""Strict three-window HTTP SLO verifier for CASE-04."""
from __future__ import annotations
import argparse, json, math, sys, time, urllib.error, urllib.request

def probe(url: str, timeout: float) -> tuple[int, float]:
    start = time.perf_counter(); status = 0
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response: response.read(); status = response.status
    except urllib.error.HTTPError as error: status = error.code
    except (OSError, TimeoutError): status = 0
    return status, (time.perf_counter() - start) * 1000.0

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--base-url", required=True)
    parser.add_argument("--windows", type=int, default=3); parser.add_argument("--requests", type=int, default=250)
    parser.add_argument("--timeout", type=float, default=1.0); args = parser.parse_args(); results = []
    for window in range(1, args.windows + 1):
        samples = [probe(f"{args.base_url.rstrip('/')}?window={window}&request={i}", args.timeout) for i in range(args.requests)]
        statuses = [x[0] for x in samples]; latencies = sorted(x[1] for x in samples)
        failures = sum(x != 200 for x in statuses); errors = sum(500 <= x < 600 for x in statuses)
        p95 = latencies[max(0, math.ceil(0.95 * len(latencies)) - 1)]; rate = errors / len(statuses)
        results.append({"window": window, "failures": failures, "http_5xx_rate": rate, "p95_latency_ms": p95,
                        "passed": failures == 0 and rate < 0.001 and p95 < 200.0})
    payload = {"thresholds": {"http_5xx_rate_lt": 0.001, "p95_latency_ms_lt": 200.0,
                              "consecutive_windows": 3}, "windows": results,
               "passed": len(results) == 3 and all(x["passed"] for x in results)}
    print(json.dumps(payload, indent=2, sort_keys=True)); return 0 if payload["passed"] else 1
if __name__ == "__main__": sys.exit(main())
