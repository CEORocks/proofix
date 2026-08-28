from proofix.baseline import ReActBaseline
from proofix.evaluator import evaluate_vrs
from proofix.policy import SafetyPolicy

from .helpers import FakeEnvironment, ScriptedBackend


def test_baseline_has_same_tools_but_fails_evidence_closure(tmp_path):
    environment = FakeEnvironment()
    backend = ScriptedBackend(
        {
            "react": [
                {
                    "kind": "action",
                    "action": {
                        "operation": "patch",
                        "target": "deployment/api",
                        "namespace": "bench",
                        "parameters": {},
                        "reversible": True,
                        "rollback": {"restore": True},
                    },
                },
                {"kind": "final", "answer": "fixed"},
            ]
        }
    )
    outcome = ReActBaseline(
        backend=backend,
        environment=environment,
        policy=SafetyPolicy(allowed_namespaces=["bench"]),
        trace_path=tmp_path / "baseline.jsonl",
        run_id="b1",
        case_id="CASE-01",
    ).run({"summary": "requests fail"})
    assert outcome.recovered
    assert not outcome.evidence_closed
    assert not evaluate_vrs(outcome).passed
