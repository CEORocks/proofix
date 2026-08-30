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


def test_proofix_records_rollback_failure_as_valid_failed_outcome(tmp_path):
    class RollbackFailureEnvironment(FakeEnvironment):
        def rollback(self, action):
            del action
            raise RuntimeError("rollout wait timed out after rollback patch applied")

    trace_path = tmp_path / "proofix.jsonl"
    workflow = ProofFixWorkflow(
        backend=ScriptedBackend(proofix_responses()),
        environment=RollbackFailureEnvironment(healthy_after_apply=False),
        policy=SafetyPolicy(allowed_namespaces=["bench"]),
        trace_path=trace_path,
        run_id="p2-rollback-error",
        case_id="CASE-05",
    )

    outcome = workflow.run({"summary": "anti-affinity blocks a replica"})

    assert outcome.disposition == "failed"
    assert not outcome.recovered
    assert "rollback incomplete" in outcome.reason
    assert "rollback_failed" in trace_path.read_text()


def test_proofix_replans_once_after_server_rejects_action(tmp_path):
    class RejectMergeEnvironment(FakeEnvironment):
        def apply(self, action):
            if action.parameters.get("patch_type") == "merge":
                raise RuntimeError("container image is required")
            return super().apply(action)

    responses = proofix_responses()
    responses["plan"]["actions"][0]["parameters"]["patch_type"] = "merge"
    revised = dict(responses["plan"])
    revised["actions"] = [dict(responses["plan"]["actions"][0])]
    revised["actions"][0]["parameters"] = {
        **responses["plan"]["actions"][0]["parameters"],
        "patch_type": "strategic",
    }
    responses["replan"] = revised
    workflow = ProofFixWorkflow(
        backend=ScriptedBackend(responses),
        environment=RejectMergeEnvironment(),
        policy=SafetyPolicy(allowed_namespaces=["bench"]),
        trace_path=tmp_path / "proofix.jsonl",
        run_id="p3",
        case_id="CASE-07",
    )
    outcome = workflow.run({"summary": "OOMKilled"})
    assert outcome.disposition == "recovered"
    assert outcome.action_count == 1
    assert evaluate_vrs(outcome).passed


def test_proofix_replans_once_after_policy_rejects_missing_rollback(tmp_path):
    responses = proofix_responses()
    rejected = dict(responses["plan"])
    rejected["actions"] = [dict(responses["plan"]["actions"][0])]
    rejected["actions"][0]["rollback"] = None
    responses["plan"] = rejected
    responses["replan"] = proofix_responses()["plan"]
    workflow = ProofFixWorkflow(
        backend=ScriptedBackend(responses),
        environment=FakeEnvironment(),
        policy=SafetyPolicy(allowed_namespaces=["bench"]),
        trace_path=tmp_path / "proofix.jsonl",
        run_id="p4",
        case_id="CASE-02",
    )

    outcome = workflow.run({"summary": "DNS failures"})

    assert outcome.disposition == "recovered"
    assert outcome.action_count == 1
    assert outcome.safe
    assert evaluate_vrs(outcome).passed


def test_proofix_records_rejected_diagnostic_and_continues(tmp_path):
    class RejectDiagnosticEnvironment(FakeEnvironment):
        def run_test(self, test):
            del test
            raise ValueError("diagnostic target is outside the registered probe")

    responses = proofix_responses()
    responses["close"]["critical_claims"][0]["evidence"] = [
        "diagnostic/error/test-0",
        "kubectl/patch#result",
    ]
    workflow = ProofFixWorkflow(
        backend=ScriptedBackend(responses),
        environment=RejectDiagnosticEnvironment(),
        policy=SafetyPolicy(allowed_namespaces=["bench"]),
        trace_path=tmp_path / "proofix.jsonl",
        run_id="p5",
        case_id="CASE-02",
    )

    outcome = workflow.run({"summary": "DNS failures"})

    assert outcome.disposition == "recovered"
    assert evaluate_vrs(outcome).passed
    assert "diagnostic/error/test-0" in (tmp_path / "proofix.jsonl").read_text()
