"""Append-only, hash-chained JSONL trajectory ledger."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


GENESIS_HASH = "0" * 64


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


class TraceLedger:
    """Writes events whose digest commits to the complete preceding history."""

    def __init__(self, path: str | Path, *, run_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._sequence = 0
        self._previous_hash = GENESIS_HASH
        if self.path.exists() and self.path.stat().st_size:
            events = list(read_events(self.path))
            ok, reason = verify_events(events)
            if not ok:
                raise ValueError(f"cannot append to invalid trace: {reason}")
            self._sequence = int(events[-1]["sequence"]) + 1
            self._previous_hash = str(events[-1]["event_hash"])

    def append(
        self,
        event_type: str,
        payload: Mapping[str, Any],
        *,
        stage: str,
        sources: Iterable[str] = (),
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "sequence": self._sequence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "event_type": event_type,
            "sources": list(sources),
            "payload": dict(payload),
            "previous_hash": self._previous_hash,
        }
        body["event_hash"] = hashlib.sha256(_canonical(body)).hexdigest()
        line = json.dumps(body, sort_keys=True, ensure_ascii=False)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        self._sequence += 1
        self._previous_hash = body["event_hash"]
        return body


def read_events(path: str | Path) -> Iterable[dict[str, Any]]:
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON at line {line_number}: {exc}") from exc


def verify_events(events: Iterable[Mapping[str, Any]]) -> tuple[bool, str]:
    previous = GENESIS_HASH
    expected_sequence = 0
    seen_run_id: str | None = None
    count = 0
    for event in events:
        count += 1
        if event.get("sequence") != expected_sequence:
            return False, f"expected sequence {expected_sequence}"
        if event.get("previous_hash") != previous:
            return False, f"broken chain at sequence {expected_sequence}"
        run_id = str(event.get("run_id", ""))
        if seen_run_id is None:
            seen_run_id = run_id
        elif run_id != seen_run_id:
            return False, "multiple run ids in one trace"
        claimed = event.get("event_hash")
        body = {key: value for key, value in event.items() if key != "event_hash"}
        actual = hashlib.sha256(_canonical(body)).hexdigest()
        if claimed != actual:
            return False, f"digest mismatch at sequence {expected_sequence}"
        previous = str(claimed)
        expected_sequence += 1
    return (count > 0, "ok" if count else "empty trace")
