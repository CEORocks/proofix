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


def test_baseline_contains_rejected_diagnostic_and_continues(tmp_path):
    class RejectDiagnosticEnvironment(FakeEnvironment):
        def run_test(self, test):
            del test
            raise ValueError("URL is outside the registered probe")

    backend = ScriptedBackend(
        {
            "react": [
                {"kind": "test", "test": {"kind": "http_get", "url": "bad"}},
                {"kind": "final", "answer": "stopped", "critical_claims": []},
            ]
        }
    )
    trace = tmp_path / "baseline.jsonl"

    outcome = ReActBaseline(
        backend=backend,
        environment=RejectDiagnosticEnvironment(),
        policy=SafetyPolicy(allowed_namespaces=["bench"]),
        trace_path=trace,
        run_id="b2",
        case_id="CASE-02",
    ).run({"summary": "DNS failures"})

    assert outcome.disposition == "failed"
    assert "diagnostic/error/react-step-0" in trace.read_text()
