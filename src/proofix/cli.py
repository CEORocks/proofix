"""Small command-line surface for verification and scoring."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .stats import summarize_pairs
from .trace import read_events, verify_events


def _verify_trace(path: str) -> int:
    try:
        valid, reason = verify_events(read_events(path))
    except (OSError, ValueError) as exc:
        valid, reason = False, str(exc)
    print(json.dumps({"path": path, "valid": valid, "reason": reason}, sort_keys=True))
    return 0 if valid else 1


def _summarize(path: str) -> int:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    result = summarize_pairs(
        [bool(row["baseline_passed"]) for row in rows],
        [bool(row["proofix_passed"]) for row in rows],
    )
    print(json.dumps(result.__dict__, indent=2, sort_keys=True))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="proofix")
    subparsers = parser.add_subparsers(dest="command", required=True)
    verify = subparsers.add_parser("verify-trace", help="verify a hash-chained JSONL trace")
    verify.add_argument("path")
    summarize = subparsers.add_parser("summarize", help="summarize paired JSON results")
    summarize.add_argument("path")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "verify-trace":
        return _verify_trace(args.path)
    if args.command == "summarize":
        return _summarize(args.path)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
