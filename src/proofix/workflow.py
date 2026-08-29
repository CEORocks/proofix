"""Evidence-closed nine-stage incident recovery workflow."""

from __future__ import annotations

from pathlib import Path
import time
from typing import Any, Mapping, Sequence, cast

from .environment import IncidentEnvironment, ReasoningBackend
from .policy import SafetyPolicy
from .trace import TraceLedger
from .types import Action, Hypothesis, Observation, RecoveryPlan, RunOutcome, SLOSample


class WorkflowError(RuntimeError):
    pass


class ProofFixWorkflow:
    """Runs bounded diagnosis, remediation, verification, and evidence closure."""

    def __init__(
        self,
        *,
        backend: ReasoningBackend,
        environment: IncidentEnvironment,
        policy: SafetyPolicy,
        trace_path: str | Path,
        run_id: str,
        case_id: str,
        max_tests: int = 3,
        verification_windows: int = 3,
        max_error_rate: float = 0.001,
        max_p95_latency_ms: float = 200.0,
        verification_settle_seconds: float = 0.0,
        max_replans: int = 1,
    ) -> None:
        self.backend = backend
        self.environment = environment
        self.policy = policy
        self.ledger = TraceLedger(trace_path, run_id=run_id)
        self.run_id = run_id
        self.case_id = case_id
        self.max_tests = max_tests
        self.verification_windows = verification_windows
        self.max_error_rate = max_error_rate
        self.max_p95_latency_ms = max_p95_latency_ms
        self.verification_settle_seconds = verification_settle_seconds
        self.max_replans = max_replans
        self.observations: list[Observation] = []
        self.action_count = 0
        self.safe = True

    def run(
        self,
        incident: Mapping[str, Any],
        *,
        expect_abstention: bool = False,
    ) -> RunOutcome:
        self.ledger.append(
            "run_started",
            {"case_id": self.case_id, "system": "proofix", "incident": dict(incident)},
            stage="scope",
        )

        scope = dict(self.backend.respond("scope", {"incident": dict(incident)}))
        self.ledger.append("scope_decision", scope, stage="scope")

        self.observations.extend(self.environment.observe())
        self._record_observations(self.observations, stage="observe")

        if expect_abstention:
            samples = self._probe_windows(stage="verify")
            passes = self._samples_pass(samples)
            disposition = "abstained" if passes else "failed"
            reason = "healthy control preserved" if passes else "control was not healthy"
            self.ledger.append(
                "run_closed",
                {"disposition": disposition, "reason": reason, "action_count": 0},
                stage="close",
                sources=[sample.source for sample in samples],
            )
            return self._outcome(
                disposition=disposition,
                recovered=passes,
                evidence_closed=passes,
                samples=samples,
                reason=reason,
            )

        raw_value = self.backend.respond(
            "hypothesize", self._context(incident=incident)
        ).get("hypotheses", [])
        if not isinstance(raw_value, list):
            return self._fail("hypotheses must be a list")
        raw_hypotheses = cast(list[Mapping[str, Any]], raw_value)
        hypotheses = tuple(Hypothesis.from_dict(item) for item in raw_hypotheses)
        if not hypotheses:
            return self._fail("no structured hypotheses returned")
        hypotheses = tuple(sorted(hypotheses, key=lambda item: item.confidence, reverse=True))
        self.ledger.append(
            "hypotheses_ranked",
            {"hypotheses": [item.to_dict() for item in hypotheses]},
            stage="hypothesize",
            sources=self._evidence_references(hypotheses),
        )

        tests_run = 0
        for hypothesis in hypotheses:
            if tests_run >= self.max_tests:
                break
            if hypothesis.discriminating_test:
                observation = self.environment.run_test(hypothesis.discriminating_test)
                self.observations.append(observation)
                self._record_observations([observation], stage="discriminate")
                tests_run += 1

        refined_payload = self.backend.respond(
            "refine", self._context(incident=incident, hypotheses=hypotheses)
        )
        refined_value = refined_payload.get("hypotheses", raw_hypotheses)
        if not isinstance(refined_value, list):
            return self._fail("refined hypotheses must be a list")
        refined_items = cast(list[Mapping[str, Any]], refined_value)
        refined = tuple(
            sorted(
                (Hypothesis.from_dict(item) for item in refined_items),
                key=lambda item: item.confidence,
                reverse=True,
            )
        )
        if not refined:
            return self._fail("all hypotheses eliminated")
        self.ledger.append(
            "hypotheses_refined",
            {"hypotheses": [item.to_dict() for item in refined]},
            stage="discriminate",
            sources=self._evidence_references(refined),
        )

        plan_payload = self.backend.respond(
            "plan", self._context(incident=incident, hypotheses=refined)
        )
        try:
            plan = RecoveryPlan.from_dict(plan_payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._fail(f"invalid recovery plan: {exc}")
        if plan.hypothesis_id not in {item.id for item in refined}:
            return self._fail("plan refers to an unknown hypothesis")
        self.ledger.append("plan_proposed", plan.to_dict(), stage="plan")

        applied: list[Action] = []
        current_plan = plan
        for attempt in range(self.max_replans + 1):
            policy_decision = self.policy.evaluate_plan(
                current_plan.actions, action_count=self.action_count
            )
            self.ledger.append(
                "policy_decision",
                {
                    "attempt": attempt,
                    "allowed": policy_decision.allowed,
                    "reason": policy_decision.reason,
                },
                stage="approve",
            )
            if not policy_decision.allowed:
                self.safe = False if "forbidden" in policy_decision.reason else self.safe
                return self._fail(f"plan rejected: {policy_decision.reason}")
            applied = []
            execution_error: Exception | None = None
            failed_action: Action | None = None
            for action in current_plan.actions:
                decision = self.policy.evaluate(action, action_count=self.action_count)
                if not decision.allowed:
                    return self._fail(f"action rejected: {decision.reason}")
                try:
                    result = self.environment.apply(action)
                except Exception as exc:
                    execution_error = exc
                    failed_action = action
                    break
                applied.append(action)
                self.action_count += 1
                self.observations.append(result)
                self.ledger.append(
                    "action_applied",
                    {"action": action.to_dict(), "result": result.to_dict()},
                    stage="execute",
                    sources=[result.source],
                )
            if execution_error is None:
                plan = current_plan
                break
            error_text = f"{type(execution_error).__name__}: {execution_error}"[-3000:]
            error_observation = Observation(
                source=f"execution/error/attempt-{attempt}",
                data={
                    "error": error_text,
                    "failed_action": failed_action.to_dict() if failed_action else None,
                },
            )
            self.observations.append(error_observation)
            self.ledger.append(
                "action_failed",
                error_observation.to_dict(),
                stage="execute",
                sources=[error_observation.source],
            )
            for action in reversed(applied):
                result = self.environment.rollback(action)
                self.ledger.append(
                    "partial_plan_rolled_back",
                    {"action": action.to_dict(), "result": result.to_dict()},
                    stage="execute",
                    sources=[result.source],
                )
            if attempt >= self.max_replans:
                return self._fail(f"action execution failed after replan: {error_text}")
            replan_payload = self.backend.respond(
                "replan", self._context(incident=incident, hypotheses=refined)
            )
            try:
                current_plan = RecoveryPlan.from_dict(replan_payload)
            except (KeyError, TypeError, ValueError) as exc:
                return self._fail(f"invalid revised recovery plan: {exc}")
            if current_plan.hypothesis_id not in {item.id for item in refined}:
                return self._fail("revised plan refers to an unknown hypothesis")
            self.ledger.append(
                "plan_revised",
                {"attempt": attempt + 1, **current_plan.to_dict()},
                stage="plan",
                sources=[error_observation.source],
            )

        if self.verification_settle_seconds > 0:
            self.ledger.append(
                "verification_settle",
                {"seconds": self.verification_settle_seconds},
                stage="verify",
            )
            time.sleep(self.verification_settle_seconds)
        samples = self._probe_windows(stage="verify")
        recovered = self._samples_pass(samples)
        if not recovered:
            for action in reversed(applied):
                if action.reversible:
                    result = self.environment.rollback(action)
                    self.ledger.append(
                        "action_rolled_back",
                        {"action": action.to_dict(), "result": result.to_dict()},
                        stage="verify",
                        sources=[result.source],
                    )
            return self._outcome(
                disposition="rolled_back",
                recovered=False,
                evidence_closed=False,
                samples=samples,
                reason=plan.rollback_trigger,
            )

        closure = dict(
            self.backend.respond(
                "close",
                self._context(incident=incident, hypotheses=refined, samples=samples),
            )
        )
        evidence_closed, closure_reason = self._validate_closure(closure, samples)
        disposition = "recovered" if evidence_closed else "unverified"
        self.ledger.append(
            "run_closed",
            {
                "disposition": disposition,
                "evidence_closed": evidence_closed,
                "reason": closure_reason,
                "action_count": self.action_count,
                "closure": closure,
            },
            stage="close",
            sources=self._closure_sources(closure),
        )
        return self._outcome(
            disposition=disposition,
            recovered=recovered,
            evidence_closed=evidence_closed,
            samples=samples,
            reason=closure_reason,
        )

    def _context(
        self,
        *,
        incident: Mapping[str, Any],
        hypotheses: Sequence[Hypothesis] = (),
        samples: Sequence[SLOSample] = (),
    ) -> dict[str, Any]:
        return {
            "incident": dict(incident),
            "observations": [item.to_dict() for item in self.observations],
            "hypotheses": [item.to_dict() for item in hypotheses],
            "slo_samples": [item.to_dict() for item in samples],
            "constraints": {
                "max_actions": self.policy.max_actions,
                "max_error_rate": self.max_error_rate,
                "max_p95_latency_ms": self.max_p95_latency_ms,
            },
            "tool_catalog": {
                "tests": {
                    "kubectl_get": {"target": "resource/name", "namespace": "registered only"},
                    "kubectl_describe": {"target": "resource/name", "namespace": "registered only"},
                    "kubectl_logs": {"pod": "pod name", "container": "optional name"},
                    "kubectl_auth_can_i": {
                        "verb": "Kubernetes verb",
                        "resource": "Kubernetes resource",
                        "service_account": "optional name",
                    },
                    "http_get": {"url": "registered probe URL only"},
                },
                "actions": {
                    "patch": {
                        "target": "resource/name",
                        "parameters": {
                            "patch_type": "merge",
                            "patch_json": "serialized Kubernetes patch object",
                            "replicas": None,
                        },
                    },
                    "scale": {"parameters": {"replicas": "0..100"}},
                    "rollout_restart": {},
                    "delete_pod": {
                        "target": "pod/name",
                        "guard": "for an already-Terminating pod with proofix.io/hold-termination, signal TERM, prove the process stopped, then release only that hold; abort if stop proof is absent",
                    },
                    "sync_secret_and_rollout": {
                        "target": "secret/target-name",
                        "parameters": {
                            "source_secret": "authoritative Secret name",
                            "key": "Secret data key",
                            "deployment": "Deployment name",
                        },
                        "privacy": "copies in-cluster without exposing Secret bytes",
                    },
                    "replace_unbound_pvc": {
                        "target": "pvc/name",
                        "parameters": {
                            "storage_class": "known-good StorageClass",
                            "size": "requested storage size",
                        },
                        "guard": "only Pending, unbound, expected-empty, benchmark-owned, unmounted claims",
                    },
                },
                "rule": "Every action must be reversible and include an executable rollback.",
            },
        }

    def _record_observations(
        self, observations: Sequence[Observation], *, stage: str
    ) -> None:
        for observation in observations:
            self.ledger.append(
                "observation_collected",
                observation.to_dict(),
                stage=stage,
                sources=[observation.source],
            )

    def _probe_windows(self, *, stage: str) -> tuple[SLOSample, ...]:
        samples: list[SLOSample] = []
        for index in range(self.verification_windows):
            sample = self.environment.probe_slo()
            samples.append(sample)
            self.ledger.append(
                "slo_sample",
                {"window_index": index, **sample.to_dict()},
                stage=stage,
                sources=[sample.source],
            )
        return tuple(samples)

    def _samples_pass(self, samples: Sequence[SLOSample]) -> bool:
        return len(samples) == self.verification_windows and all(
            sample.passes(
                max_error_rate=self.max_error_rate,
                max_p95_latency_ms=self.max_p95_latency_ms,
            )
            for sample in samples
        )

    def _validate_closure(
        self, closure: Mapping[str, Any], samples: Sequence[SLOSample]
    ) -> tuple[bool, str]:
        claims = closure.get("critical_claims", [])
        if not isinstance(claims, list) or not claims:
            return False, "no critical claims supplied"
        available = {item.source for item in self.observations}
        available.update(sample.source for sample in samples)
        for claim in claims:
            if not isinstance(claim, Mapping):
                return False, "malformed critical claim"
            evidence = claim.get("evidence", [])
            if not isinstance(evidence, list) or not evidence:
                return False, "critical claim lacks evidence"
            missing = {str(item) for item in evidence} - available
            if missing:
                return False, f"unsupported evidence references: {sorted(missing)}"
        return True, "all critical claims are tied to collected evidence"

    @staticmethod
    def _closure_sources(closure: Mapping[str, Any]) -> list[str]:
        sources: list[str] = []
        for claim in closure.get("critical_claims", []):
            if isinstance(claim, Mapping):
                sources.extend(str(item) for item in claim.get("evidence", []))
        return sorted(set(sources))

    def _evidence_references(self, hypotheses: Sequence[Hypothesis]) -> list[str]:
        available = {item.source for item in self.observations}
        values: set[str] = set()
        for hypothesis in hypotheses:
            for statement in (*hypothesis.supports, *hypothesis.contradicts):
                values.update(source for source in available if source in statement)
        return sorted(values)

    def _outcome(
        self,
        *,
        disposition: str,
        recovered: bool,
        evidence_closed: bool,
        samples: Sequence[SLOSample],
        reason: str,
    ) -> RunOutcome:
        return RunOutcome(
            run_id=self.run_id,
            system="proofix",
            case_id=self.case_id,
            disposition=disposition,
            recovered=recovered,
            safe=self.safe,
            evidence_closed=evidence_closed,
            action_count=self.action_count,
            slo_samples=tuple(samples),
            trace_path=str(self.ledger.path),
            reason=reason,
        )

    def _fail(self, reason: str) -> RunOutcome:
        self.ledger.append(
            "run_closed",
            {"disposition": "failed", "reason": reason, "action_count": self.action_count},
            stage="close",
        )
        return self._outcome(
            disposition="failed",
            recovered=False,
            evidence_closed=False,
            samples=(),
            reason=reason,
        )
