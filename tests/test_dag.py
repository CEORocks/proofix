"""Behavioral tests for the SQLite DAG coordinator."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from proofix.dag import DAGCoordinator, SubmissionConflict, TaskNotFound  # noqa: E402


class MutableClock:
    def __init__(self, value: float = 1_000.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


class DAGCoordinatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database = Path(self.temporary_directory.name) / "coordinator.db"
        self.clock = MutableClock()
        self.coordinator = DAGCoordinator(self.database, clock=self.clock)
        self.coordinator.initialize()

    def tearDown(self) -> None:
        self.coordinator.close()
        self.temporary_directory.cleanup()

    def test_dependencies_must_all_complete_before_child_is_claimable(self) -> None:
        self.coordinator.submit_tasks(
            [
                {"id": "c-child", "depends_on": ["a-parent", "b-parent"]},
                {"id": "b-parent"},
                {"id": "a-parent"},
            ]
        )

        first = self.coordinator.claim("worker", lease_seconds=30)
        self.assertIsNotNone(first)
        self.assertEqual(first["task_id"], "a-parent")
        self.coordinator.complete("a-parent", "worker")

        second = self.coordinator.claim("worker", lease_seconds=30)
        self.assertIsNotNone(second)
        self.assertEqual(second["task_id"], "b-parent")
        self.assertEqual(self.coordinator.get_task("c-child")["state"], "pending")
        self.coordinator.complete("b-parent", "worker")

        child = self.coordinator.claim("worker", lease_seconds=30)
        self.assertIsNotNone(child)
        self.assertEqual(child["task_id"], "c-child")

    def test_two_connections_cannot_claim_the_same_task(self) -> None:
        self.coordinator.submit_task("only-task")
        first_connection = DAGCoordinator(self.database, clock=self.clock)
        second_connection = DAGCoordinator(self.database, clock=self.clock)
        barrier = threading.Barrier(3)
        results: list[dict[str, object] | None] = []
        errors: list[BaseException] = []

        def race(coordinator: DAGCoordinator, owner: str) -> None:
            try:
                barrier.wait(timeout=2)
                results.append(coordinator.claim(owner, lease_seconds=30))
            except BaseException as exc:  # Preserve worker failures for the main assertion.
                errors.append(exc)

        threads = [
            threading.Thread(target=race, args=(first_connection, "worker-a")),
            threading.Thread(target=race, args=(second_connection, "worker-b")),
        ]
        try:
            for thread in threads:
                thread.start()
            barrier.wait(timeout=2)
            for thread in threads:
                thread.join(timeout=3)

            self.assertFalse(any(thread.is_alive() for thread in threads))
            self.assertEqual(errors, [])
            claimed = [task for task in results if task is not None]
            self.assertEqual(len(claimed), 1)
            self.assertEqual(claimed[0]["task_id"], "only-task")
            self.assertEqual(self.coordinator.get_task("only-task")["attempts"], 1)
        finally:
            first_connection.close()
            second_connection.close()

    def test_expired_lease_is_requeued_and_claimed_by_another_worker(self) -> None:
        self.coordinator.submit_task("recoverable", max_attempts=2)
        claimed = self.coordinator.claim("dead-worker", lease_seconds=10)
        self.assertIsNotNone(claimed)

        self.clock.value = 1_011.0
        reaped = self.coordinator.reap_expired()
        self.assertEqual([task["task_id"] for task in reaped], ["recoverable"])
        self.assertEqual(reaped[0]["state"], "pending")
        self.assertIsNone(reaped[0]["lease_owner"])

        reclaimed = self.coordinator.claim("replacement", lease_seconds=10)
        self.assertIsNotNone(reclaimed)
        self.assertEqual(reclaimed["lease_owner"], "replacement")
        self.assertEqual(reclaimed["attempts"], 2)
        self.assertIn("lease_expired_requeued", self._event_types("recoverable"))

    def test_heartbeat_extends_lease_and_prevents_early_reap(self) -> None:
        self.coordinator.submit_task("long-running", max_attempts=2)
        claimed = self.coordinator.claim("worker", lease_seconds=10)
        self.assertEqual(claimed["lease_expires_at"], 1_010.0)

        self.clock.value = 1_005.0
        heartbeat = self.coordinator.heartbeat("long-running", "worker", lease_seconds=20)
        self.assertEqual(heartbeat["lease_expires_at"], 1_025.0)

        self.clock.value = 1_011.0
        self.assertEqual(self.coordinator.reap_expired(), [])
        self.assertEqual(self.coordinator.get_task("long-running")["state"], "running")

        self.clock.value = 1_026.0
        self.assertEqual(len(self.coordinator.reap_expired()), 1)
        self.assertEqual(self.coordinator.get_task("long-running")["state"], "pending")

    def test_failure_retries_then_exhausts_max_attempts(self) -> None:
        self.coordinator.submit_task("flaky", max_attempts=2)

        first = self.coordinator.claim("worker", lease_seconds=30)
        self.assertEqual(first["attempts"], 1)
        retry = self.coordinator.fail("flaky", "worker", "first failure")
        self.assertEqual(retry["state"], "pending")
        self.assertEqual(retry["last_error"], "first failure")

        second = self.coordinator.claim("worker", lease_seconds=30)
        self.assertEqual(second["attempts"], 2)
        exhausted = self.coordinator.fail("flaky", "worker", "second failure")
        self.assertEqual(exhausted["state"], "failed")
        self.assertEqual(exhausted["attempts"], 2)
        self.assertIsNone(self.coordinator.claim("worker", lease_seconds=30))
        self.assertEqual(
            self._event_types("flaky"),
            ["submitted", "claimed", "failed_requeued", "claimed", "failed_exhausted"],
        )

    def test_final_attempt_lease_expiry_exhausts_task(self) -> None:
        self.coordinator.submit_task("one-shot", max_attempts=1)
        self.coordinator.claim("lost-worker", lease_seconds=5)
        self.clock.value = 1_006.0

        reaped = self.coordinator.reap_expired()
        self.assertEqual(reaped[0]["state"], "failed")
        self.assertEqual(reaped[0]["last_error"], "lease expired after final attempt")
        self.assertIsNone(self.coordinator.claim("other", lease_seconds=5))

    def test_submission_is_idempotent_and_conflicts_are_atomic(self) -> None:
        definition = [
            {"id": "root", "payload": {"kind": "observe"}, "max_attempts": 2},
            {
                "id": "child",
                "payload": {"kind": "verify"},
                "depends_on": ["root"],
                "max_attempts": 4,
            },
        ]
        first = self.coordinator.submit_tasks(definition)
        second = self.coordinator.submit_tasks(definition)
        self.assertTrue(all(task["created"] for task in first))
        self.assertTrue(all(not task["created"] for task in second))
        self.assertEqual(len(self.coordinator.events()), 2)

        with self.assertRaises(SubmissionConflict):
            self.coordinator.submit_tasks(
                [
                    {"id": "new-task"},
                    {"id": "root", "payload": {"kind": "changed"}, "max_attempts": 2},
                ]
            )
        with self.assertRaises(TaskNotFound):
            self.coordinator.get_task("new-task")
        self.assertEqual(len(self.coordinator.status()["tasks"]), 2)

    def _event_types(self, task_id: str) -> list[str]:
        return [event["event_type"] for event in self.coordinator.events(task_id)]


class CoordinatorCLITests(unittest.TestCase):
    def test_all_commands_emit_json_and_drive_a_task_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database = root / "state" / "coordinator.db"
            submission = root / "tasks.json"
            submission.write_text(
                json.dumps({"tasks": [{"id": "success"}, {"id": "retry", "max_attempts": 1}]}),
                encoding="utf-8",
            )

            self.assertTrue(self._command(database, "init")["ok"])
            submitted = self._command(database, "submit-json", str(submission))
            self.assertEqual(submitted["created"], 2)

            claimed = self._command(
                database, "claim", "--owner", "cli-worker", "--lease-seconds", "5"
            )
            self.assertEqual(claimed["task"]["task_id"], "retry")
            heartbeat = self._command(
                database,
                "heartbeat",
                "retry",
                "--owner",
                "cli-worker",
                "--lease-seconds",
                "5",
            )
            self.assertEqual(heartbeat["task"]["state"], "running")
            failed = self._command(
                database,
                "fail",
                "retry",
                "--owner",
                "cli-worker",
                "--error",
                "expected",
            )
            self.assertEqual(failed["task"]["state"], "failed")

            self._command(
                database, "claim", "--owner", "cli-worker", "--lease-seconds", "5"
            )
            completed = self._command(
                database,
                "complete",
                "success",
                "--owner",
                "cli-worker",
                "--result-json",
                '{"verified":true}',
            )
            self.assertEqual(completed["task"]["result"], {"verified": True})
            self.assertEqual(self._command(database, "reap")["reaped"], 0)
            status = self._command(database, "status")
            self.assertEqual(status["summary"]["completed"], 1)
            self.assertEqual(status["summary"]["failed"], 1)

    @staticmethod
    def _command(database: Path, *arguments: str) -> dict[str, object]:
        completed = subprocess.run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "scripts" / "coordinator.py"),
                "--db",
                str(database),
                *arguments,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"CLI failed ({completed.returncode}): {completed.stderr or completed.stdout}"
            )
        output = json.loads(completed.stdout)
        if not isinstance(output, dict):
            raise AssertionError(f"CLI did not return a JSON object: {completed.stdout}")
        return output


if __name__ == "__main__":
    unittest.main()
