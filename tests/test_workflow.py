from proofix.evaluator import evaluate_vrs
from proofix.policy import SafetyPolicy
from proofix.workflow import ProofFixWorkflow

from .helpers import FakeEnvironment, ScriptedBackend, proofix_responses


def test_proofix_recovers_with_evidence_and_three_slo_windows(tmp_path):
    environment = FakeEnvironment()
    workflow = ProofFixWorkflow(
        backend=ScriptedBackend(proofix_responses()),
        environment=environment,
        policy=SafetyPolicy(allowed_namespaces=["bench"]),
        trace_path=tmp_path / "proofix.jsonl",
        run_id="p1",
        case_id="CASE-01",
    )
    outcome = workflow.run({"summary": "requests fail"})
    assert outcome.disposition == "recovered"
    assert outcome.evidence_closed
    assert len(outcome.slo_samples) == 3
    assert evaluate_vrs(outcome).passed


def test_proofix_rolls_back_when_slo_does_not_recover(tmp_path):
    environment = FakeEnvironment(healthy_after_apply=False)
    workflow = ProofFixWorkflow(
        backend=ScriptedBackend(proofix_responses()),
        environment=environment,
        policy=SafetyPolicy(allowed_namespaces=["bench"]),
        trace_path=tmp_path / "proofix.jsonl",
        run_id="p2",
        case_id="CASE-01",
    )
    outcome = workflow.run({"summary": "requests fail"})
    assert outcome.disposition == "rolled_back"
    assert environment.rolled_back
    assert not evaluate_vrs(outcome).passed
