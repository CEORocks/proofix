from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from proofix.backends import AntigravityBackend, schema_for


def _fake_agy(tmp_path: Path) -> Path:
    executable = tmp_path / "agy"
    executable.write_text(
        f"""#!{sys.executable}
import json
import os
import sys

mode = os.environ.get("FAKE_AGY_MODE", "success")
if mode == "exit":
    print("worker failed", file=sys.stderr)
    raise SystemExit(7)
if mode == "malformed":
    print("not-json")
    raise SystemExit(0)
if mode == "canceled":
    print(json.dumps({{"status": "CANCELED", "error": "quota"}}))
    raise SystemExit(0)
if mode == "missing":
    print(json.dumps({{"status": "SUCCESS"}}))
    raise SystemExit(0)
print(json.dumps({{
    "status": "SUCCESS",
    "structured_output": {{
        "namespace": "bench",
        "impact": "degraded",
        "constraints": ["bounded"]
    }}
}}))
""",
        encoding="utf-8",
    )
    executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
    return executable


def test_antigravity_success_passes_flash_schema_and_sandbox(
    tmp_path: Path,
) -> None:
    executable = _fake_agy(tmp_path)
    log = tmp_path / "argv.json"
    wrapper = tmp_path / "wrapper"
    wrapper.write_text(
        f"""#!{sys.executable}
import json
import subprocess
import sys
from pathlib import Path
Path({str(log)!r}).write_text(json.dumps(sys.argv[1:]), encoding="utf-8")
raise SystemExit(subprocess.run([{str(executable)!r}, *sys.argv[1:]]).returncode)
""",
        encoding="utf-8",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)

    result = AntigravityBackend(agy_binary=str(wrapper)).respond(
        "scope", {"case": "01", "evidence": "x" * 200_000}
    )

    assert result["namespace"] == "bench"
    argv = json.loads(log.read_text(encoding="utf-8"))
    assert argv[argv.index("--model") + 1] == "gemini-3.7-flash-medium"
    assert "--sandbox" in argv
    assert "--dangerously-skip-permissions" not in argv
    assert argv[argv.index("--input-format") + 1] == "stream-json"
    assert argv[argv.index("--output-format") + 1] == "stream-json"
    assert "--print" not in argv
    assert json.loads(argv[argv.index("--json-schema") + 1]) == schema_for("scope")


@pytest.mark.parametrize(
    ("mode", "message"),
    [
        ("exit", r"failed \(7\)"),
        ("malformed", "result event"),
        ("canceled", "unsuccessful status"),
        ("missing", "missing structured_output"),
    ],
)
def test_antigravity_rejects_worker_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    message: str,
) -> None:
    monkeypatch.setenv("FAKE_AGY_MODE", mode)
    backend = AntigravityBackend(agy_binary=str(_fake_agy(tmp_path)))
    with pytest.raises(RuntimeError, match=message):
        backend.respond("scope", {})
