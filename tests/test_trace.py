import json

from proofix.trace import TraceLedger, read_events, verify_events


def test_hash_chain_detects_tampering(tmp_path):
    path = tmp_path / "run.jsonl"
    ledger = TraceLedger(path, run_id="r1")
    ledger.append("one", {"value": 1}, stage="scope")
    ledger.append("two", {"value": 2}, stage="observe")
    assert verify_events(read_events(path)) == (True, "ok")

    rows = path.read_text().splitlines()
    event = json.loads(rows[0])
    event["payload"]["value"] = 99
    rows[0] = json.dumps(event)
    path.write_text("\n".join(rows) + "\n")
    valid, reason = verify_events(read_events(path))
    assert not valid
    assert "digest mismatch" in reason


def test_ledger_can_safely_resume(tmp_path):
    path = tmp_path / "run.jsonl"
    TraceLedger(path, run_id="r1").append("one", {}, stage="scope")
    TraceLedger(path, run_id="r1").append("two", {}, stage="observe")
    events = list(read_events(path))
    assert [event["sequence"] for event in events] == [0, 1]
    assert verify_events(events)[0]
