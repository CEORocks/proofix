"""Dependency-free paired benchmark statistics."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Iterable, Sequence


@dataclass(frozen=True)
class PairedSummary:
    pairs: int
    baseline_rate: float
    proofix_rate: float
    lift_percentage_points: float
    bootstrap_ci_low: float
    bootstrap_ci_high: float
    discordant_proofix_wins: int
    discordant_baseline_wins: int
    mcnemar_exact_p: float


def summarize_pairs(
    baseline: Sequence[bool],
    proofix: Sequence[bool],
    *,
    bootstrap_samples: int = 10_000,
    seed: int = 2026,
) -> PairedSummary:
    if len(baseline) != len(proofix) or not baseline:
        raise ValueError("baseline and ProofFix must contain the same non-zero number of runs")
    size = len(baseline)
    baseline_rate = sum(baseline) / size
    proofix_rate = sum(proofix) / size
    rng = random.Random(seed)
    lifts: list[float] = []
    for _ in range(bootstrap_samples):
        indices = [rng.randrange(size) for _ in range(size)]
        base_rate = sum(baseline[index] for index in indices) / size
        agent_rate = sum(proofix[index] for index in indices) / size
        lifts.append(agent_rate - base_rate)
    lifts.sort()
    lower = lifts[int(0.025 * (bootstrap_samples - 1))]
    upper = lifts[int(0.975 * (bootstrap_samples - 1))]
    proofix_wins = sum(not left and right for left, right in zip(baseline, proofix))
    baseline_wins = sum(left and not right for left, right in zip(baseline, proofix))
    return PairedSummary(
        pairs=size,
        baseline_rate=baseline_rate,
        proofix_rate=proofix_rate,
        lift_percentage_points=(proofix_rate - baseline_rate) * 100.0,
        bootstrap_ci_low=lower * 100.0,
        bootstrap_ci_high=upper * 100.0,
        discordant_proofix_wins=proofix_wins,
        discordant_baseline_wins=baseline_wins,
        mcnemar_exact_p=_mcnemar_exact(proofix_wins, baseline_wins),
    )


def _mcnemar_exact(left_only: int, right_only: int) -> float:
    discordant = left_only + right_only
    if discordant == 0:
        return 1.0
    smaller = min(left_only, right_only)
    tail = sum(math.comb(discordant, index) for index in range(smaller + 1)) / (2**discordant)
    return float(min(1.0, 2.0 * tail))


def booleans(values: Iterable[object]) -> list[bool]:
    return [bool(value) for value in values]
