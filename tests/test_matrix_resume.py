from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from proofix.runner import FixtureController


def load_run_matrix():
    path = Path(__file__).resolve().parents[1] / "scripts" / "run_matrix.py"
    spec = importlib.util.spec_from_file_location("proofix_run_matrix", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_resume_skips_only_valid_system_keys(tmp_path, monkeypatch) -> None:
    module = load_run_matrix()
    results = tmp_path / "results.jsonl"
    rows = [
        {"case_id": "CASE-10", "system": "react", "trial": 1, "valid": True},
        {"case_id": "CASE-10", "system": "proofix", "trial": 1, "valid": False},
        {"case_id": "CASE-10", "system": "proofix", "trial": 1, "valid": True},
        {"case_id": "CASE-11", "system": "react", "trial": 2, "valid": False},
    ]
    results.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    monkeypatch.setattr(module, "RESULTS", results)

    assert module.completed_keys() == {
        ("CASE-10", "react", 1),
        ("CASE-10", "proofix", 1),
    }


def test_fixture_lifecycle_allows_slow_cold_start(monkeypatch) -> None:
    observed: dict[str, object] = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["timeout"] = kwargs["timeout"]
        return SimpleNamespace(returncode=0, stdout="ready\n", stderr="")

    monkeypatch.setattr("proofix.runner.subprocess.run", fake_run)
    controller = FixtureController(
        host="local",
        fixture_dir="/tmp/proofix-fixture",
        kubeconfig="/tmp/kubeconfig",
    )

    assert controller.run("install.sh") == "ready\n"
    assert observed["timeout"] == 1200
