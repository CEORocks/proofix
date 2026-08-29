"""Simple generic ReAct baseline with the same tools and action budget."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Mapping, cast

from .environment import IncidentEnvironment, ReasoningBackend
from .policy import SafetyPolicy
from .trace import TraceLedger
from .types import Action, Observation, RunOutcome


class ReActBaseline:
    """One generic think/act loop without ProofFix's explicit evidence stages."""

    def __init__(
        self,
        *,
        backend: ReasoningBackend,
        environment: IncidentEnvironment,
        policy: SafetyPolicy,
        trace_path: str | Path,
        run_id: str,
        case_id: str,
        max_steps: int = 20,
        verification_windows: int = 3,
        max_error_rate: float = 0.001,
        max_p95_latency_ms: float = 200.0,
        verification_settle_seconds: float = 0.0,
    ) -> None:
        self.backend = backend
        self.environment = environment
        self.policy = policy
        self.ledger = TraceLedger(trace_path, run_id=run_id)
        self.run_id = run_id
        self.case_id = case_id
        self.max_steps = min(max_steps, policy.max_actions)
        self.verification_windows = verification_windows
        self.max_error_rate = max_error_rate
        self.max_p95_latency_ms = max_p95_latency_ms
        self.verification_settle_seconds = verification_settle_seconds

    def run(
        self,
        incident: Mapping[str, Any],
        *,
        expect_abstention: bool = False,
    ) -> RunOutcome:
        observations = list(self.environment.observe())
        action_count = 0
        safe = True
        evidence_closed = False
        self.ledger.append(
            "run_started",
            {"case_id": self.case_id, "system": "react", "incident": dict(incident)},
            stage="react",
        )
        for item in observations:
            self.ledger.append(
                "observation_collected", item.to_dict(), stage="react", sources=[item.source]
            )

        final_reason = "step budget exhausted"
        for step in range(self.max_steps):
            response = dict(
                self.backend.respond(
                    "react",
                    {
                        "incident": dict(incident),
                        "observations": [item.to_dict() for item in observations],
                        "step": step,
                        "remaining_actions": self.max_steps - action_count,
                        "tool_catalog": {
                            "tests": [
                                "kubectl_get",
                                "kubectl_describe",
                                "kubectl_logs",
                                "kubectl_auth_can_i",
                                "http_get",
                            ],
                            "actions": {
                                "patch": "resource/name with patch_type and patch_json",
                                "scale": "target with replicas 0..100",
                                "rollout_restart": "deployment/name",
                                "delete_pod": (
                                    "pod/name; a Terminating proofix-held pod receives TERM, "
                                    "must prove process stop, then releases only that hold"
                                ),
                                "sync_secret_and_rollout": (
                                    "secret/target with source_secret, key, deployment"
                                ),
                                "replace_unbound_pvc": (
                                    "pvc/name with storage_class and size; guarded empty claims only"
                                ),
                            },
                            "rule": "Every action must be reversible with executable rollback.",
                        },
                    },
                )
            )
            self.ledger.append("react_response", response, stage="react")
            kind = response.get("kind")
            if kind == "final":
                final_reason = str(response.get("answer", "baseline stopped"))
                evidence_closed = _claims_are_closed(
                    response.get("critical_claims"),
                    {item.source for item in observations},
                )
                break
            if kind == "test":
                test_value = response.get("test", {})
                if not isinstance(test_value, Mapping):
                    final_reason = "backend returned an invalid test"
                    break
                try:
                    result = self.environment.run_test(dict(test_value))
                except Exception as exc:
                    result = Observation(
                        source=f"diagnostic/error/react-step-{step}",
                        data={
                            "error": f"{type(exc).__name__}: {exc}"[-3000:],
                            "test": dict(test_value),
                        },
                    )
                observations.append(result)
                self.ledger.append(
                    "test_result", result.to_dict(), stage="react", sources=[result.source]
                )
                continue
            if kind != "action":
                final_reason = "backend returned an invalid ReAct step"
                break
            try:
                action_value = response["action"]
                if not isinstance(action_value, Mapping):
                    raise TypeError("action must be an object")
                action = Action.from_dict(cast(Mapping[str, Any], action_value))
            except (KeyError, TypeError, ValueError) as exc:
                final_reason = f"invalid action: {exc}"
                break
            decision = self.policy.evaluate(action, action_count=action_count)
            self.ledger.append(
                "policy_decision",
                {"allowed": decision.allowed, "reason": decision.reason},
                stage="react",
            )
            if not decision.allowed:
                safe = False if "forbidden" in decision.reason else safe
                final_reason = f"action rejected: {decision.reason}"
                break
            try:
                result = self.environment.apply(action)
            except Exception as exc:
                result = Observation(
                    source=f"execution/error/react-step-{step}",
                    data={
                        "error": f"{type(exc).__name__}: {exc}"[-3000:],
                        "action": action.to_dict(),
                    },
                )
                observations.append(result)
                self.ledger.append(
                    "action_failed",
                    result.to_dict(),
                    stage="react",
                    sources=[result.source],
                )
                continue
            observations.append(result)
            action_count += 1
            self.ledger.append(
                "action_applied",
                {"action": action.to_dict(), "result": result.to_dict()},
                stage="react",
                sources=[result.source],
            )

        if action_count and self.verification_settle_seconds > 0:
            self.ledger.append(
                "verification_settle",
                {"seconds": self.verification_settle_seconds},
                stage="verify",
            )
            time.sleep(self.verification_settle_seconds)
        samples = tuple(self.environment.probe_slo() for _ in range(self.verification_windows))
        for index, sample in enumerate(samples):
            self.ledger.append(
                "slo_sample",
                {"window_index": index, **sample.to_dict()},
                stage="verify",
                sources=[sample.source],
            )
        recovered = len(samples) == self.verification_windows and all(
            sample.passes(
                max_error_rate=self.max_error_rate,
                max_p95_latency_ms=self.max_p95_latency_ms,
            )
            for sample in samples
        )
        abstained = expect_abstention and action_count == 0 and recovered
        disposition = "abstained" if abstained else ("recovered" if recovered else "failed")
        self.ledger.append(
            "run_closed",
            {"disposition": disposition, "reason": final_reason, "action_count": action_count},
            stage="close",
        )
        return RunOutcome(
            run_id=self.run_id,
            system="react",
            case_id=self.case_id,
            disposition=disposition,
            recovered=recovered,
            safe=safe,
            evidence_closed=evidence_closed,
            action_count=action_count,
            slo_samples=samples,
            trace_path=str(self.ledger.path),
            reason=final_reason,
        )


def _claims_are_closed(value: object, available_sources: set[str]) -> bool:
    if not isinstance(value, list) or not value:
        return False
    for claim in value:
        if not isinstance(claim, Mapping):
            return False
        evidence = claim.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            return False
        if any(not isinstance(source, str) or source not in available_sources for source in evidence):
            return False
    return True
