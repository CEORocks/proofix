from __future__ import annotations

from collections import deque
from typing import Any, Mapping

from proofix.types import Action, Observation, SLOSample


class ScriptedBackend:
    def __init__(self, responses: Mapping[str, list[Mapping[str, object]] | Mapping[str, object]]):
        self.responses: dict[str, deque[Mapping[str, object]]] = {}
        for stage, values in responses.items():
            if isinstance(values, list):
                self.responses[stage] = deque(values)
            else:
                self.responses[stage] = deque([values])

    def respond(self, stage: str, context: Mapping[str, object]) -> Mapping[str, object]:
        del context
        queue = self.responses[stage]
        if len(queue) > 1:
            return queue.popleft()
        return queue[0]


class FakeEnvironment:
    def __init__(self, *, healthy_after_apply: bool = True):
        self.healthy = False
        self.healthy_after_apply = healthy_after_apply
        self.applied: list[Action] = []
        self.rolled_back: list[Action] = []

    def observe(self) -> list[Observation]:
        return [Observation("kubectl/pods#initial", {"ready": False, "restarts": 4})]

    def run_test(self, test: Mapping[str, object]) -> Observation:
        return Observation("kubectl/configmap#test", {"test": dict(test), "mismatch": True})

    def apply(self, action: Action) -> Observation:
        self.applied.append(action)
        self.healthy = self.healthy_after_apply
        return Observation("kubectl/patch#result", {"changed": True})

    def rollback(self, action: Action) -> Observation:
        self.rolled_back.append(action)
        self.healthy = False
        return Observation("kubectl/rollback#result", {"rolled_back": True})

    def probe_slo(self) -> SLOSample:
        if self.healthy:
            return SLOSample(0.0, 80.0, True, "probe/http", 10)
        return SLOSample(0.2, 900.0, False, "probe/http", 10)


def proofix_responses() -> dict[str, Any]:
    hypothesis = {
        "id": "h1",
        "cause": "configuration mismatch",
        "confidence": 0.8,
        "supports": ["kubectl/pods#initial"],
        "contradicts": [],
        "discriminating_test": {"kind": "inspect_config"},
    }
    return {
        "scope": {"namespace": "bench", "impact": "availability"},
        "hypothesize": {"hypotheses": [hypothesis]},
        "refine": {"hypotheses": [hypothesis]},
        "plan": {
            "hypothesis_id": "h1",
            "rationale": "correct the observed mismatch",
            "actions": [
                {
                    "operation": "patch",
                    "target": "deployment/api",
                    "namespace": "bench",
                    "parameters": {"path": "spec.template.metadata.labels.version", "value": "v1"},
                    "reversible": True,
                    "rollback": {"value": "broken"},
                }
            ],
            "success_criteria": {"slo": "strict"},
            "rollback_trigger": "three SLO windows fail",
        },
        "close": {
            "critical_claims": [
                {
                    "claim": "configuration mismatch was repaired",
                    "evidence": ["kubectl/configmap#test", "kubectl/patch#result"],
                }
            ]
        },
    }
