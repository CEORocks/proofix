"""Deterministic safety gate for all environment mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .types import Action


MUTATING_OPERATIONS = frozenset(
    {
        "patch",
        "apply",
        "rollout_restart",
        "scale",
        "delete_pod",
        "sync_secret_and_rollout",
        "replace_unbound_pvc",
        "cordon",
        "uncordon",
    }
)

FORBIDDEN_OPERATIONS = frozenset(
    {
        "delete_namespace",
        "delete_pvc",
        "delete_pv",
        "delete_database",
        "drop_database",
        "wipe_volume",
        "format_disk",
        "force_detach_volume",
        "disable_auth",
        "grant_cluster_admin",
    }
)


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


class SafetyPolicy:
    def __init__(
        self,
        *,
        allowed_namespaces: Iterable[str],
        max_actions: int = 20,
        allow_irreversible: bool = False,
    ) -> None:
        self.allowed_namespaces = frozenset(allowed_namespaces)
        self.max_actions = max_actions
        self.allow_irreversible = allow_irreversible

    def evaluate(self, action: Action, *, action_count: int) -> PolicyDecision:
        operation = action.operation.strip().lower()
        target = action.target.strip().lower()
        if action_count >= self.max_actions:
            return PolicyDecision(False, "action budget exhausted")
        if action.namespace not in self.allowed_namespaces:
            return PolicyDecision(False, f"namespace {action.namespace!r} is outside scope")
        if operation in FORBIDDEN_OPERATIONS:
            return PolicyDecision(False, f"operation {operation!r} is forbidden")
        if any(token in target for token in ("persistentvolume", "database")) and operation.startswith("delete"):
            return PolicyDecision(False, "deletion of stateful data resources is forbidden")
        if operation not in MUTATING_OPERATIONS:
            return PolicyDecision(False, f"operation {operation!r} is not allowlisted")
        if not action.reversible and not self.allow_irreversible:
            return PolicyDecision(False, "irreversible action requires human approval")
        if action.reversible and not action.rollback:
            return PolicyDecision(False, "reversible action is missing a rollback specification")
        return PolicyDecision(True, "allowed")

    def evaluate_plan(self, actions: Iterable[Action], *, action_count: int = 0) -> PolicyDecision:
        for offset, action in enumerate(actions):
            decision = self.evaluate(action, action_count=action_count + offset)
            if not decision.allowed:
                return decision
        return PolicyDecision(True, "allowed")
