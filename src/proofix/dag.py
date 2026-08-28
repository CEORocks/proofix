"""SQLite-backed DAG coordination with renewable worker leases.

Task definitions are immutable after submission.  Runtime transitions and their
corresponding event records are committed in the same SQLite transaction, which
makes the database both the coordinator state and its audit trail.
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence, cast


TASK_STATES = ("pending", "running", "completed", "failed")


class DAGError(RuntimeError):
    """Base class for coordinator errors."""


class InvalidTask(DAGError):
    """A submitted task definition is invalid."""


class SubmissionConflict(DAGError):
    """A task ID was resubmitted with a different immutable definition."""


class TaskNotFound(DAGError):
    """The requested task does not exist."""


class LeaseError(DAGError):
    """The caller does not hold a current lease for the task."""


_SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id          TEXT PRIMARY KEY,
    payload_json     TEXT NOT NULL,
    state            TEXT NOT NULL DEFAULT 'pending'
                     CHECK (state IN ('pending', 'running', 'completed', 'failed')),
    attempts         INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts     INTEGER NOT NULL CHECK (max_attempts > 0),
    lease_owner      TEXT,
    lease_expires_at REAL,
    result_json      TEXT,
    last_error       TEXT,
    created_at       REAL NOT NULL,
    updated_at       REAL NOT NULL,
    CHECK (
        (state = 'running' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
        OR
        (state <> 'running' AND lease_owner IS NULL AND lease_expires_at IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS dependencies (
    task_id       TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    depends_on_id TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE RESTRICT,
    PRIMARY KEY (task_id, depends_on_id),
    CHECK (task_id <> depends_on_id)
);

CREATE TABLE IF NOT EXISTS task_events (
    event_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id      TEXT NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    event_type   TEXT NOT NULL,
    lease_owner  TEXT,
    details_json TEXT NOT NULL,
    created_at   REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_claim
    ON tasks(state, created_at, task_id);
CREATE INDEX IF NOT EXISTS idx_tasks_lease
    ON tasks(state, lease_expires_at);
CREATE INDEX IF NOT EXISTS idx_dependencies_parent
    ON dependencies(depends_on_id);
CREATE INDEX IF NOT EXISTS idx_task_events_task
    ON task_events(task_id, event_id);
PRAGMA user_version = 1;
"""


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError) as exc:
        raise InvalidTask(f"value is not valid JSON: {exc}") from exc


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidTask(f"{field} must be a non-empty string")
    return value


class DAGCoordinator:
    """Coordinate immutable DAG tasks through a SQLite database.

    One instance owns one SQLite connection.  Workers should create separate
    instances pointing at the same database; ``BEGIN IMMEDIATE`` serializes all
    claim decisions across those connections.
    """

    def __init__(
        self,
        database: str | Path,
        *,
        timeout: float = 5.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.database = str(database)
        self._clock = clock
        self._connection = sqlite3.connect(
            self.database,
            timeout=timeout,
            isolation_level=None,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute(f"PRAGMA busy_timeout = {max(0, int(timeout * 1000))}")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._connection.execute("PRAGMA synchronous = NORMAL")

    def __enter__(self) -> DAGCoordinator:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        self._connection.close()

    def initialize(self) -> None:
        """Create the version-one schema if it is not already present."""

        self._connection.executescript(_SCHEMA)

    @contextmanager
    def _immediate(self) -> Iterator[None]:
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self._connection.rollback()
            raise
        else:
            self._connection.commit()

    def _now(self, supplied: float | None) -> float:
        value = self._clock() if supplied is None else supplied
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("now must be a numeric Unix timestamp")
        return float(value)

    def _event(
        self,
        task_id: str,
        event_type: str,
        *,
        owner: str | None,
        details: Mapping[str, Any],
        now: float,
    ) -> None:
        self._connection.execute(
            """
            INSERT INTO task_events(task_id, event_type, lease_owner, details_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, event_type, owner, _json_dumps(dict(details)), now),
        )

    @staticmethod
    def _normalize_task(raw: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise InvalidTask("each task must be a JSON object")

        raw_id = raw.get("id", raw.get("task_id"))
        task_id = _nonempty_string(raw_id, "task id")
        if "id" in raw and "task_id" in raw and raw["id"] != raw["task_id"]:
            raise InvalidTask(f"task {task_id!r} has conflicting id fields")

        raw_dependencies = raw.get("depends_on", raw.get("dependencies", []))
        if isinstance(raw_dependencies, (str, bytes)) or not isinstance(
            raw_dependencies, Sequence
        ):
            raise InvalidTask(f"task {task_id!r} dependencies must be a list")
        dependencies = sorted(
            {_nonempty_string(dependency, "dependency id") for dependency in raw_dependencies}
        )
        if "depends_on" in raw and "dependencies" in raw:
            alternate = raw["dependencies"]
            if isinstance(alternate, (str, bytes)) or not isinstance(alternate, Sequence):
                raise InvalidTask(f"task {task_id!r} dependencies must be a list")
            alternate_dependencies = {
                _nonempty_string(dependency, "dependency id") for dependency in alternate
            }
            if set(dependencies) != alternate_dependencies:
                raise InvalidTask(f"task {task_id!r} has conflicting dependency fields")
        if task_id in dependencies:
            raise InvalidTask(f"task {task_id!r} cannot depend on itself")

        max_attempts = raw.get("max_attempts", 3)
        if isinstance(max_attempts, bool) or not isinstance(max_attempts, int):
            raise InvalidTask(f"task {task_id!r} max_attempts must be an integer")
        if max_attempts < 1:
            raise InvalidTask(f"task {task_id!r} max_attempts must be positive")

        payload = raw.get("payload", {})
        return {
            "task_id": task_id,
            "payload": payload,
            "payload_json": _json_dumps(payload),
            "dependencies": dependencies,
            "max_attempts": max_attempts,
        }

    def submit_task(
        self,
        task_id: str,
        payload: Any = None,
        *,
        dependencies: Sequence[str] = (),
        max_attempts: int = 3,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Submit one task, returning its state and whether it was created."""

        submitted = self.submit_tasks(
            [
                {
                    "id": task_id,
                    "payload": {} if payload is None else payload,
                    "depends_on": list(dependencies),
                    "max_attempts": max_attempts,
                }
            ],
            now=now,
        )
        return submitted[0]

    def submit_tasks(
        self,
        tasks: Iterable[Mapping[str, Any]],
        *,
        now: float | None = None,
    ) -> list[dict[str, Any]]:
        """Atomically submit a set of tasks.

        Repeating the exact submission is a no-op.  Reusing a task ID with a
        different payload, dependency set, or retry budget raises
        :class:`SubmissionConflict` and rolls back the complete batch.
        """

        normalized = [self._normalize_task(task) for task in tasks]
        seen: set[str] = set()
        for task in normalized:
            task_id = task["task_id"]
            if task_id in seen:
                raise InvalidTask(f"duplicate task id in submission: {task_id!r}")
            seen.add(task_id)
        timestamp = self._now(now)
        created_ids: set[str] = set()

        with self._immediate():
            for task in normalized:
                task_id = task["task_id"]
                existing = self._connection.execute(
                    "SELECT payload_json, max_attempts FROM tasks WHERE task_id = ?",
                    (task_id,),
                ).fetchone()
                if existing is None:
                    self._connection.execute(
                        """
                        INSERT INTO tasks(
                            task_id, payload_json, max_attempts, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            task_id,
                            task["payload_json"],
                            task["max_attempts"],
                            timestamp,
                            timestamp,
                        ),
                    )
                    created_ids.add(task_id)
                    continue

                current_dependencies = {
                    row["depends_on_id"]
                    for row in self._connection.execute(
                        "SELECT depends_on_id FROM dependencies WHERE task_id = ?",
                        (task_id,),
                    )
                }
                if (
                    existing["payload_json"] != task["payload_json"]
                    or existing["max_attempts"] != task["max_attempts"]
                    or current_dependencies != set(task["dependencies"])
                ):
                    raise SubmissionConflict(
                        f"task {task_id!r} already exists with a different definition"
                    )

            for task in normalized:
                task_id = task["task_id"]
                for dependency in task["dependencies"]:
                    exists = self._connection.execute(
                        "SELECT 1 FROM tasks WHERE task_id = ?", (dependency,)
                    ).fetchone()
                    if exists is None:
                        raise InvalidTask(
                            f"task {task_id!r} has unknown dependency {dependency!r}"
                        )
                    if task_id in created_ids:
                        self._connection.execute(
                            "INSERT INTO dependencies(task_id, depends_on_id) VALUES (?, ?)",
                            (task_id, dependency),
                        )

            cycle = self._connection.execute(
                """
                WITH RECURSIVE paths(task_id, depends_on_id) AS (
                    SELECT task_id, depends_on_id FROM dependencies
                    UNION
                    SELECT paths.task_id, dependencies.depends_on_id
                    FROM paths
                    JOIN dependencies ON dependencies.task_id = paths.depends_on_id
                )
                SELECT task_id FROM paths WHERE task_id = depends_on_id LIMIT 1
                """
            ).fetchone()
            if cycle is not None:
                raise InvalidTask(f"dependency cycle includes task {cycle['task_id']!r}")

            for task in normalized:
                if task["task_id"] not in created_ids:
                    continue
                self._event(
                    task["task_id"],
                    "submitted",
                    owner=None,
                    details={},
                    now=timestamp,
                )

            result = []
            for task in normalized:
                task_state = self._get_task_locked(task["task_id"])
                task_state["created"] = task["task_id"] in created_ids
                result.append(task_state)
            return result

    def _get_task_locked(self, task_id: str) -> dict[str, Any]:
        row = self._connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise TaskNotFound(f"task {task_id!r} does not exist")
        dependencies = [
            dependency["depends_on_id"]
            for dependency in self._connection.execute(
                """
                SELECT depends_on_id FROM dependencies
                WHERE task_id = ? ORDER BY depends_on_id
                """,
                (task_id,),
            )
        ]
        return {
            "task_id": row["task_id"],
            "payload": json.loads(row["payload_json"]),
            "state": row["state"],
            "attempts": row["attempts"],
            "max_attempts": row["max_attempts"],
            "dependencies": dependencies,
            "lease_owner": row["lease_owner"],
            "lease_expires_at": row["lease_expires_at"],
            "result": None if row["result_json"] is None else json.loads(row["result_json"]),
            "last_error": row["last_error"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def get_task(self, task_id: str) -> dict[str, Any]:
        return self._get_task_locked(_nonempty_string(task_id, "task id"))

    def _reap_expired_locked(self, now: float) -> list[str]:
        rows = self._connection.execute(
            """
            SELECT task_id, lease_owner, attempts, max_attempts
            FROM tasks
            WHERE state = 'running' AND lease_expires_at <= ?
            ORDER BY task_id
            """,
            (now,),
        ).fetchall()
        reaped: list[str] = []
        for row in rows:
            exhausted = row["attempts"] >= row["max_attempts"]
            new_state = "failed" if exhausted else "pending"
            last_error = "lease expired after final attempt" if exhausted else "lease expired"
            self._connection.execute(
                """
                UPDATE tasks
                SET state = ?, lease_owner = NULL, lease_expires_at = NULL,
                    last_error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (new_state, last_error, now, row["task_id"]),
            )
            self._event(
                row["task_id"],
                "lease_expired_exhausted" if exhausted else "lease_expired_requeued",
                owner=row["lease_owner"],
                details={"attempt": row["attempts"]},
                now=now,
            )
            reaped.append(row["task_id"])
        return reaped

    def reap_expired(self, *, now: float | None = None) -> list[dict[str, Any]]:
        """Requeue expired leases, or fail them if their retry budget is spent."""

        timestamp = self._now(now)
        with self._immediate():
            task_ids = self._reap_expired_locked(timestamp)
            return [self._get_task_locked(task_id) for task_id in task_ids]

    def claim(
        self,
        owner: str,
        *,
        lease_seconds: float = 60.0,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        """Atomically claim the next runnable task for ``owner``.

        Runnable means pending, within its retry budget, and with every direct
        dependency completed.  Expired leases are reaped in the same write
        transaction before selection.
        """

        lease_owner = _nonempty_string(owner, "lease owner")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, (int, float)):
            raise ValueError("lease_seconds must be numeric")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        timestamp = self._now(now)
        expiry = timestamp + float(lease_seconds)

        with self._immediate():
            self._reap_expired_locked(timestamp)
            row = self._connection.execute(
                """
                SELECT task_id
                FROM tasks
                WHERE state = 'pending'
                  AND attempts < max_attempts
                  AND NOT EXISTS (
                      SELECT 1
                      FROM dependencies
                      JOIN tasks AS prerequisite
                        ON prerequisite.task_id = dependencies.depends_on_id
                      WHERE dependencies.task_id = tasks.task_id
                        AND prerequisite.state <> 'completed'
                  )
                ORDER BY created_at, task_id
                LIMIT 1
                """
            ).fetchone()
            if row is None:
                return None

            self._connection.execute(
                """
                UPDATE tasks
                SET state = 'running', attempts = attempts + 1,
                    lease_owner = ?, lease_expires_at = ?, updated_at = ?
                WHERE task_id = ? AND state = 'pending'
                """,
                (lease_owner, expiry, timestamp, row["task_id"]),
            )
            task = self._get_task_locked(row["task_id"])
            self._event(
                row["task_id"],
                "claimed",
                owner=lease_owner,
                details={"attempt": task["attempts"], "lease_expires_at": expiry},
                now=timestamp,
            )
            return task

    def _require_active_lease(
        self, task_id: str, owner: str, now: float
    ) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM tasks WHERE task_id = ?", (task_id,)
        ).fetchone()
        if row is None:
            raise TaskNotFound(f"task {task_id!r} does not exist")
        if row["state"] != "running":
            raise LeaseError(f"task {task_id!r} is not running")
        if row["lease_owner"] != owner:
            raise LeaseError(f"worker {owner!r} does not own task {task_id!r}")
        if row["lease_expires_at"] <= now:
            raise LeaseError(f"lease for task {task_id!r} has expired")
        return cast(sqlite3.Row, row)

    def heartbeat(
        self,
        task_id: str,
        owner: str,
        *,
        lease_seconds: float = 60.0,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Extend an active lease from the heartbeat time."""

        task_key = _nonempty_string(task_id, "task id")
        lease_owner = _nonempty_string(owner, "lease owner")
        if isinstance(lease_seconds, bool) or not isinstance(lease_seconds, (int, float)):
            raise ValueError("lease_seconds must be numeric")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        timestamp = self._now(now)
        expiry = timestamp + float(lease_seconds)

        with self._immediate():
            row = self._require_active_lease(task_key, lease_owner, timestamp)
            self._connection.execute(
                """
                UPDATE tasks SET lease_expires_at = ?, updated_at = ? WHERE task_id = ?
                """,
                (expiry, timestamp, task_key),
            )
            self._event(
                task_key,
                "heartbeat",
                owner=lease_owner,
                details={"attempt": row["attempts"], "lease_expires_at": expiry},
                now=timestamp,
            )
            return self._get_task_locked(task_key)

    def complete(
        self,
        task_id: str,
        owner: str,
        *,
        result: Any = None,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Complete a task while holding its active lease."""

        task_key = _nonempty_string(task_id, "task id")
        lease_owner = _nonempty_string(owner, "lease owner")
        result_json = _json_dumps(result)
        timestamp = self._now(now)
        with self._immediate():
            row = self._require_active_lease(task_key, lease_owner, timestamp)
            self._connection.execute(
                """
                UPDATE tasks
                SET state = 'completed', lease_owner = NULL, lease_expires_at = NULL,
                    result_json = ?, last_error = NULL, updated_at = ?
                WHERE task_id = ?
                """,
                (result_json, timestamp, task_key),
            )
            self._event(
                task_key,
                "completed",
                owner=lease_owner,
                details={"attempt": row["attempts"]},
                now=timestamp,
            )
            return self._get_task_locked(task_key)

    def fail(
        self,
        task_id: str,
        owner: str,
        error: str,
        *,
        now: float | None = None,
    ) -> dict[str, Any]:
        """Record a failed attempt and either requeue or exhaust the task."""

        task_key = _nonempty_string(task_id, "task id")
        lease_owner = _nonempty_string(owner, "lease owner")
        failure = _nonempty_string(error, "error")
        timestamp = self._now(now)
        with self._immediate():
            row = self._require_active_lease(task_key, lease_owner, timestamp)
            exhausted = row["attempts"] >= row["max_attempts"]
            new_state = "failed" if exhausted else "pending"
            self._connection.execute(
                """
                UPDATE tasks
                SET state = ?, lease_owner = NULL, lease_expires_at = NULL,
                    last_error = ?, updated_at = ?
                WHERE task_id = ?
                """,
                (new_state, failure, timestamp, task_key),
            )
            self._event(
                task_key,
                "failed_exhausted" if exhausted else "failed_requeued",
                owner=lease_owner,
                details={"attempt": row["attempts"], "error": failure},
                now=timestamp,
            )
            return self._get_task_locked(task_key)

    def status(self, task_id: str | None = None) -> dict[str, Any]:
        """Return task records and counts by state."""

        if task_id is None:
            task_ids = [
                row["task_id"]
                for row in self._connection.execute(
                    "SELECT task_id FROM tasks ORDER BY created_at, task_id"
                )
            ]
        else:
            task_ids = [_nonempty_string(task_id, "task id")]
        tasks = [self._get_task_locked(current) for current in task_ids]
        summary = {state: 0 for state in TASK_STATES}
        for task in tasks:
            summary[task["state"]] += 1
        return {"summary": summary, "tasks": tasks}

    def events(self, task_id: str | None = None) -> list[dict[str, Any]]:
        """Read the append-only task event stream in commit order."""

        if task_id is None:
            rows = self._connection.execute(
                "SELECT * FROM task_events ORDER BY event_id"
            ).fetchall()
        else:
            task_key = _nonempty_string(task_id, "task id")
            rows = self._connection.execute(
                "SELECT * FROM task_events WHERE task_id = ? ORDER BY event_id",
                (task_key,),
            ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "task_id": row["task_id"],
                "event_type": row["event_type"],
                "lease_owner": row["lease_owner"],
                "details": json.loads(row["details_json"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]


__all__ = [
    "DAGCoordinator",
    "DAGError",
    "InvalidTask",
    "LeaseError",
    "SubmissionConflict",
    "TaskNotFound",
]
