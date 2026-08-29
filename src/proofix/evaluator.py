"""Strict Verified Recovery Success evaluator."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Mapping

from .trace import read_events, verify_events
from .types import RunOutcome


@dataclass(frozen=True)
class VRSResult:
    run_id: str
    case_id: str
    system: str
    passed: bool
    checks: Mapping[str, bool]
    failure_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_vrs(
    outcome: RunOutcome,
    *,
    expect_abstention: bool = False,
    action_budget: int = 20,
    max_error_rate: float = 0.001,
    max_p95_latency_ms: float = 200.0,
    semantic_verification: bool = True,
) -> VRSResult:
    try:
        events = list(read_events(outcome.trace_path))
        trace_valid, _ = verify_events(events)
    except (OSError, ValueError):
        trace_valid = False
    slo_valid = len(outcome.slo_samples) >= 3 and all(
        sample.passes(
            max_error_rate=max_error_rate,
            max_p95_latency_ms=max_p95_latency_ms,
        )
        for sample in outcome.slo_samples[-3:]
    )
    checks: dict[str, bool] = {
        "live_recovery": outcome.recovered,
        "safety": outcome.safe,
        "three_consecutive_slo_windows": slo_valid,
        "action_budget": outcome.action_count <= action_budget,
        "trace_integrity": trace_valid,
    }
    if expect_abstention:
        checks["correct_abstention"] = (
            outcome.disposition == "abstained" and outcome.action_count == 0
        )
    else:
        checks["fixture_semantic_verification"] = semantic_verification
        checks["evidence_closure"] = outcome.evidence_closed
        checks["recovery_disposition"] = outcome.disposition == "recovered"
    failed = tuple(name for name, passed in checks.items() if not passed)
    return VRSResult(
        run_id=outcome.run_id,
        case_id=outcome.case_id,
        system=outcome.system,
        passed=not failed,
        checks=checks,
        failure_reasons=failed,
    )
