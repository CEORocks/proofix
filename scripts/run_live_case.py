#!/usr/bin/env python3
"""CLI wrapper around one isolated ProofFix live run."""

from __future__ import annotations

import argparse
import json

from proofix.runner import LiveRunConfig, run_live


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-path", required=True)
    parser.add_argument("--system", choices=("react", "proofix"), required=True)
    parser.add_argument("--trial", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--remote-fixture-dir", required=True)
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--workload-selector", required=True)
    parser.add_argument("--node-port", type=int, required=True)
    parser.add_argument("--local-port", type=int, required=True)
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--probe-path", default="/")
    parser.add_argument("--probe-requests", type=int, default=1000)
    parser.add_argument("--window-seconds", type=int, default=10)
    args = parser.parse_args()
    result = run_live(LiveRunConfig(**vars(args)))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
