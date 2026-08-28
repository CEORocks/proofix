from proofix.policy import SafetyPolicy
from proofix.types import Action


def action(**overrides):
    values = {
        "operation": "patch",
        "target": "deployment/api",
        "namespace": "bench",
        "parameters": {},
        "reversible": True,
        "rollback": {"restore": True},
    }
    values.update(overrides)
    return Action(**values)


def test_policy_allows_scoped_reversible_patch():
    decision = SafetyPolicy(allowed_namespaces=["bench"]).evaluate(action(), action_count=0)
    assert decision.allowed


def test_policy_blocks_stateful_deletion_and_scope_escape():
    policy = SafetyPolicy(allowed_namespaces=["bench"])
    assert not policy.evaluate(action(operation="delete_pvc"), action_count=0).allowed
    assert not policy.evaluate(action(namespace="production"), action_count=0).allowed


def test_policy_enforces_action_budget_and_rollback():
    policy = SafetyPolicy(allowed_namespaces=["bench"], max_actions=1)
    assert not policy.evaluate(action(), action_count=1).allowed
    assert not policy.evaluate(action(rollback=None), action_count=0).allowed
