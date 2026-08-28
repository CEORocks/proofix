"""Runtime boundary between reasoning and the incident environment."""

from __future__ import annotations

from typing import Mapping, Protocol, Sequence

from .types import Action, Observation, SLOSample


class IncidentEnvironment(Protocol):
    """The same interface is used by Kubernetes and deterministic test doubles."""

    def observe(self) -> Sequence[Observation]: ...

    def run_test(self, test: Mapping[str, object]) -> Observation: ...

    def apply(self, action: Action) -> Observation: ...

    def rollback(self, action: Action) -> Observation: ...

    def probe_slo(self) -> SLOSample: ...


class ReasoningBackend(Protocol):
    """Model-independent structured reasoning contract."""

    def respond(self, stage: str, context: Mapping[str, object]) -> Mapping[str, object]: ...
