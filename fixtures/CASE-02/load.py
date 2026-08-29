#!/usr/bin/env python3
"""Live DNS evidence and strict HTTP SLO verifier for CASE-02."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class WindowResult:
    window: int
    requests: int
    failures: int
    http_5xx: int
    http_5xx_rate: float
    p95_latency_ms: float
    passed: bool


def request(url: str, timeout: float = 2.0) -> tuple[int, float, bytes]:
    started = time.perf_counter()
    status = 0
    body = b""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        status = error.code
        body = error.read()
    except (OSError, TimeoutError):
        status = 0
    return status, (time.perf_counter() - started) * 1000.0, body


def percentile_nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return ordered[rank - 1]


def diagnostics(base_url: str) -> dict[str, Any]:
    status, http_latency, body = request(f"{base_url}/diagnostics")
    if status != 200:
        raise RuntimeError(f"diagnostics returned HTTP {status}")
    evidence = json.loads(body)
    evidence["diagnostics_http_latency_ms"] = round(http_latency, 3)
    return evidence


def verify_dns(base_url: str, expect: str) -> int:
    evidence = diagnostics(base_url)
    if expect == "fault":
        passed = (
            evidence.get("rcode") == 3
            and evidence.get("answer_ip") is None
            and evidence.get("latency_ms", 0) >= 300.0
            and not evidence.get("ok")
        )
    else:
        passed = (
            evidence.get("rcode") == 0
            and evidence.get("answer_ip") == "198.51.100.42"
            and evidence.get("latency_ms", 1000) < 200.0
            and evidence.get("ok") is True
        )
    payload = {"mode": "dns", "expect": expect, "evidence": evidence, "passed": passed}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if passed else 1


def verify_incident(base_url: str) -> int:
    status, latency, body = request(f"{base_url}/checkout")
    try:
        evidence = json.loads(body)
    except json.JSONDecodeError:
        evidence = {"raw_body": body.decode(errors="replace")}
    passed = status == 503 and latency >= 300.0 and evidence.get("rcode") == 3
    print(json.dumps({"mode": "incident", "status": status,
                      "latency_ms": round(latency, 3), "evidence": evidence,
                      "passed": passed}, indent=2, sort_keys=True))
    return 0 if passed else 1


def verify_slo(base_url: str, requests: int) -> int:
    results: list[WindowResult] = []
    for window in range(1, 4):
        latencies: list[float] = []
        failures = 0
        http_5xx = 0
        for index in range(requests):
            status, latency, _ = request(
                f"{base_url}/checkout?window={window}&request={index}"
            )
            latencies.append(latency)
            failures += status != 200
            http_5xx += 500 <= status <= 599
        rate = http_5xx / requests
        p95 = percentile_nearest_rank(latencies, 0.95)
        passed = failures == 0 and rate < 0.001 and p95 < 200.0
        results.append(WindowResult(window, requests, failures, http_5xx, rate, p95, passed))
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
    subparsers = parser.add_subparsers(dest="command", required=True)
    dns = subparsers.add_parser("dns")
    dns.add_argument("--base-url", default="http://127.0.0.1:30072")
    dns.add_argument("--expect", choices=("fault", "recovered"), required=True)
    incident = subparsers.add_parser("incident")
    incident.add_argument("--base-url", default="http://127.0.0.1:30072")
    slo = subparsers.add_parser("slo")
    slo.add_argument("--base-url", default="http://127.0.0.1:30072")
    slo.add_argument("--requests", type=int, default=250)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if args.command == "dns":
        return verify_dns(base_url, args.expect)
    if args.command == "incident":
        return verify_incident(base_url)
    return verify_slo(base_url, args.requests)


if __name__ == "__main__":
    sys.exit(main())

