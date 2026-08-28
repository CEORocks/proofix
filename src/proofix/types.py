"""Typed domain objects shared by the ProofFix runtime.

The objects deliberately serialize to plain JSON so every decision can be
replayed without importing a model SDK or a Kubernetes client.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping


JSON = dict[str, Any]


@dataclass(frozen=True)
class Action:
    operation: str
    target: str
    namespace: str
    parameters: Mapping[str, Any] = field(default_factory=dict)
    reversible: bool = True
    rollback: Mapping[str, Any] | None = None

    def to_dict(self) -> JSON:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Action":
        return cls(
            operation=str(value["operation"]),
            target=str(value["target"]),
            namespace=str(value["namespace"]),
            parameters=dict(value.get("parameters", {})),
            reversible=bool(value.get("reversible", True)),
            rollback=(
                dict(value["rollback"])
                if value.get("rollback") is not None
                else None
            ),
        )


@dataclass(frozen=True)
class Observation:
    source: str
    data: Mapping[str, Any]
    collected_at: str | None = None

    def to_dict(self) -> JSON:
        return asdict(self)


@dataclass(frozen=True)
class Hypothesis:
    id: str
    cause: str
    confidence: float
    supports: tuple[str, ...] = ()
    contradicts: tuple[str, ...] = ()
    discriminating_test: Mapping[str, Any] | None = None

    def to_dict(self) -> JSON:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Hypothesis":
        confidence = float(value.get("confidence", 0.0))
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("hypothesis confidence must be between 0 and 1")
        test = value.get("discriminating_test")
        return cls(
            id=str(value["id"]),
            cause=str(value["cause"]),
            confidence=confidence,
            supports=tuple(str(item) for item in value.get("supports", ())),
            contradicts=tuple(str(item) for item in value.get("contradicts", ())),
            discriminating_test=dict(test) if test is not None else None,
        )


@dataclass(frozen=True)
class RecoveryPlan:
    hypothesis_id: str
    rationale: str
    actions: tuple[Action, ...]
    success_criteria: Mapping[str, Any]
    rollback_trigger: str

    def to_dict(self) -> JSON:
        return {
            "hypothesis_id": self.hypothesis_id,
            "rationale": self.rationale,
            "actions": [action.to_dict() for action in self.actions],
            "success_criteria": dict(self.success_criteria),
            "rollback_trigger": self.rollback_trigger,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RecoveryPlan":
        return cls(
            hypothesis_id=str(value["hypothesis_id"]),
            rationale=str(value["rationale"]),
            actions=tuple(Action.from_dict(item) for item in value.get("actions", ())),
            success_criteria=dict(value.get("success_criteria", {})),
            rollback_trigger=str(value.get("rollback_trigger", "verification failed")),
        )


@dataclass(frozen=True)
class SLOSample:
    error_rate: float
    p95_latency_ms: float
    healthy: bool
    source: str
    window_seconds: int

    def passes(self, *, max_error_rate: float, max_p95_latency_ms: float) -> bool:
        return (
            self.healthy
            and self.error_rate < max_error_rate
            and self.p95_latency_ms < max_p95_latency_ms
        )

    def to_dict(self) -> JSON:
        return asdict(self)


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    system: str
    case_id: str
    disposition: str
    recovered: bool
    safe: bool
    evidence_closed: bool
    action_count: int
    slo_samples: tuple[SLOSample, ...]
    trace_path: str
    reason: str = ""

    def to_dict(self) -> JSON:
        return {
            **asdict(self),
            "slo_samples": [sample.to_dict() for sample in self.slo_samples],
        }
