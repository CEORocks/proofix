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
    parser.add_argument("--additional-namespace", action="append", default=[])
    parser.add_argument("--fixture-env", action="append", default=[])
    parser.add_argument("--workload-selector", required=True)
    parser.add_argument("--node-port", type=int, required=True)
    parser.add_argument("--service-name", default="")
    parser.add_argument("--service-port", type=int, default=80)
    parser.add_argument("--local-port", type=int, required=True)
    parser.add_argument("--backend", choices=("codex", "antigravity"), default="codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--kubeconfig", default="/etc/rancher/k3s/k3s.yaml")
    parser.add_argument("--probe-path", default="/")
    parser.add_argument("--probe-requests", type=int, default=1000)
    parser.add_argument("--window-seconds", type=int, default=10)
    parser.add_argument("--verification-settle-seconds", type=float, default=5.0)
    args = parser.parse_args()
    values = vars(args)
    if values["model"] is None:
        values["model"] = (
            "gemini-3.7-flash-medium"
            if values["backend"] == "antigravity"
            else "gpt-5.6-sol"
        )
    values["additional_namespaces"] = tuple(values.pop("additional_namespace"))
    fixture_environment = []
    for item in values.pop("fixture_env"):
        key, separator, value = item.partition("=")
        if not separator or not key:
            parser.error("--fixture-env must use KEY=VALUE")
        fixture_environment.append((key, value))
    values["fixture_environment"] = tuple(fixture_environment)
    result = run_live(LiveRunConfig(**values))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get("valid") else 1


if __name__ == "__main__":
    raise SystemExit(main())
