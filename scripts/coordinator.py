#!/usr/bin/env python3
"""JSON command-line interface for the ProofFix DAG coordinator."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, NoReturn, Sequence


# Permit direct execution from a clean repository checkout without installation.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _REPOSITORY_ROOT / "src"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

from proofix.dag import DAGCoordinator, DAGError  # noqa: E402


class JSONArgumentParser(argparse.ArgumentParser):
    """Emit parser failures as machine-readable JSON."""

    def error(self, message: str) -> NoReturn:
        _emit({"ok": False, "error": {"type": "usage_error", "message": message}}, sys.stderr)
        raise SystemExit(2)


def _emit(value: Any, stream: Any = sys.stdout) -> None:
    print(json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True), file=stream)


def _read_json(source: str) -> Any:
    if source == "-":
        return json.load(sys.stdin)
    with open(source, encoding="utf-8") as handle:
        return json.load(handle)


def _json_argument(value: str) -> Any:
    if value.startswith("@"):
        return _read_json(value[1:])
    return json.loads(value)


def _tasks_from_document(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        tasks = document
    elif isinstance(document, dict) and "tasks" in document:
        tasks = document["tasks"]
    elif isinstance(document, dict):
        tasks = [document]
    else:
        raise ValueError("submission JSON must be a task, a task list, or an object with 'tasks'")
    if not isinstance(tasks, list) or not all(isinstance(task, dict) for task in tasks):
        raise ValueError("'tasks' must be a list of JSON objects")
    return tasks


def _parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.environ.get("PROOFIX_COORDINATOR_DB", "state/coordinator.db"),
        help="SQLite database path (default: state/coordinator.db)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("init", help="create the coordinator schema")

    submit = commands.add_parser("submit-json", help="atomically submit tasks from JSON")
    submit.add_argument("source", help="JSON file path, or - for standard input")

    claim = commands.add_parser("claim", help="claim the next runnable task")
    claim.add_argument("--owner", required=True)
    claim.add_argument("--lease-seconds", type=float, default=60.0)

    heartbeat = commands.add_parser("heartbeat", help="extend an active task lease")
    heartbeat.add_argument("task_id")
    heartbeat.add_argument("--owner", required=True)
    heartbeat.add_argument("--lease-seconds", type=float, default=60.0)

    complete = commands.add_parser("complete", help="complete a leased task")
    complete.add_argument("task_id")
    complete.add_argument("--owner", required=True)
    complete.add_argument(
        "--result-json",
        default="null",
        help="inline JSON, or @path to read JSON from a file",
    )

    fail = commands.add_parser("fail", help="fail and retry or exhaust a leased task")
    fail.add_argument("task_id")
    fail.add_argument("--owner", required=True)
    fail.add_argument("--error", required=True)

    status = commands.add_parser("status", help="show coordinator task state")
    status.add_argument("--task-id")

    commands.add_parser("reap", help="requeue or exhaust expired leases")
    return parser


def _run(args: argparse.Namespace) -> dict[str, Any]:
    database = Path(args.db)
    if args.command == "init":
        database.parent.mkdir(parents=True, exist_ok=True)

    with DAGCoordinator(database) as coordinator:
        if args.command == "init":
            coordinator.initialize()
            return {"ok": True, "command": "init", "database": str(database)}
        if args.command == "submit-json":
            tasks = coordinator.submit_tasks(_tasks_from_document(_read_json(args.source)))
            return {
                "ok": True,
                "command": "submit-json",
                "submitted": len(tasks),
                "created": sum(bool(task.pop("created")) for task in tasks),
                "tasks": tasks,
            }
        if args.command == "claim":
            task = coordinator.claim(args.owner, lease_seconds=args.lease_seconds)
            return {"ok": True, "command": "claim", "claimed": task is not None, "task": task}
        if args.command == "heartbeat":
            task = coordinator.heartbeat(
                args.task_id, args.owner, lease_seconds=args.lease_seconds
            )
            return {"ok": True, "command": "heartbeat", "task": task}
        if args.command == "complete":
            task = coordinator.complete(
                args.task_id, args.owner, result=_json_argument(args.result_json)
            )
            return {"ok": True, "command": "complete", "task": task}
        if args.command == "fail":
            task = coordinator.fail(args.task_id, args.owner, args.error)
            return {"ok": True, "command": "fail", "task": task}
        if args.command == "status":
            return {"ok": True, "command": "status", **coordinator.status(args.task_id)}
        if args.command == "reap":
            tasks = coordinator.reap_expired()
            return {
                "ok": True,
                "command": "reap",
                "reaped": len(tasks),
                "tasks": tasks,
            }
    raise AssertionError(f"unhandled command: {args.command}")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        response = _run(args)
    except (DAGError, OSError, sqlite3.Error, json.JSONDecodeError, ValueError) as exc:
        _emit(
            {
                "ok": False,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
            sys.stderr,
        )
        return 1
    _emit(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
