#!/usr/bin/env python3
"""Render the isolated CASE-02 CoreDNS block without touching other zones."""

from __future__ import annotations

import argparse
import ipaddress
import re
import sys


BEGIN = "# BEGIN PROOFIX CASE-02"
END = "# END PROOFIX CASE-02"
MANAGED = re.compile(
    rf"\n?{re.escape(BEGIN)}.*?{re.escape(END)}\n?", re.DOTALL
)


def render(corefile: str, target: str) -> str:
    host, separator, port = target.partition(":")
    ipaddress.ip_address(host)
    if separator != ":" or port != "5353":
        raise ValueError("target must be an IP address followed by :5353")
    clean = MANAGED.sub("\n", corefile).rstrip()
    block = f"""
{BEGIN}
bench.proofix:53 {{
    errors
    log
    forward . {target} {{
        max_fails 0
        expire 1s
    }}
}}
{END}
""".strip()
    return f"{clean}\n\n{block}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    args = parser.parse_args()
    sys.stdout.write(render(sys.stdin.read(), args.target))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

