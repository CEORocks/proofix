#!/usr/bin/env python3
"""Freeze, validate, and summarize the distributed ProofFix benchmark."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from proofix.stats import summarize_pairs
from proofix.trace import read_events, verify_events


SYSTEM_ORDER = {"react": 0, "proofix": 1}


def _rows(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError(f"non-object row in {path}")
                rows.append(value)
    return rows


def _key(row: dict[str, Any]) -> tuple[str, str, int]:
    return str(row["case_id"]), str(row["system"]), int(row["trial"])


def _expected_keys() -> set[tuple[str, str, int]]:
    return {
        (f"CASE-{case:02}", system, trial)
        for case in range(1, 16)
        for system in ("react", "proofix")
        for trial in (1, 2, 3)
    }


def _select_valid(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if bool(row.get("valid")):
            grouped[_key(row)].append(row)
    expected = _expected_keys()
    missing = sorted(expected - set(grouped))
    extra = sorted(set(grouped) - expected)
    if missing or extra:
        raise ValueError(f"matrix key mismatch: missing={missing}, extra={extra}")
    selected = [max(candidates, key=lambda row: str(row["run_id"])) for candidates in grouped.values()]
    return sorted(
        selected,
        key=lambda row: (
            int(str(row["case_id"])[-2:]),
            int(row["trial"]),
            SYSTEM_ORDER[str(row["system"])],
        ),
    )


def _validate_artifacts(rows: list[dict[str, Any]], runs_root: Path) -> dict[str, int]:
    event_count = 0
    for row in rows:
        run_dir = runs_root / str(row["run_id"])
        result_path = run_dir / "result.json"
        snapshot_path = run_dir / "initial-snapshot.json"
        trace_path = run_dir / "trajectory.jsonl"
        for path in (result_path, snapshot_path, trace_path):
            if not path.is_file() or path.stat().st_size == 0:
                raise ValueError(f"missing or empty artifact: {path}")
        artifact_result = json.loads(result_path.read_text(encoding="utf-8"))
        if _key(artifact_result) != _key(row) or not bool(artifact_result.get("valid")):
            raise ValueError(f"result artifact mismatch: {result_path}")
        events = list(read_events(trace_path))
        ok, reason = verify_events(events)
        if not ok:
            raise ValueError(f"invalid trajectory {trace_path}: {reason}")
        if any(str(event.get("run_id")) != str(row["run_id"]) for event in events):
            raise ValueError(f"trajectory run id mismatch: {trace_path}")
        event_count += len(events)
    return {"verified_results": len(rows), "verified_trajectories": len(rows), "events": event_count}


def _rate(rows: list[dict[str, Any]], field: str) -> float:
    return sum(bool(row["outcome"].get(field)) for row in rows) / len(rows)


def _summary(rows: list[dict[str, Any]], integrity: dict[str, int]) -> dict[str, Any]:
    by_key = {_key(row): row for row in rows}
    baseline: list[bool] = []
    proofix: list[bool] = []
    for case in range(1, 16):
        for trial in (1, 2, 3):
            baseline.append(bool(by_key[(f"CASE-{case:02}", "react", trial)]["vrs"]["passed"]))
            proofix.append(bool(by_key[(f"CASE-{case:02}", "proofix", trial)]["vrs"]["passed"]))
    paired = summarize_pairs(baseline, proofix)
    systems: dict[str, Any] = {}
    for system in ("react", "proofix"):
        items = [row for row in rows if row["system"] == system]
        control = [row for row in items if row["case_id"] == "CASE-15"]
        systems[system] = {
            "runs": len(items),
            "vrs_passes": sum(bool(row["vrs"]["passed"]) for row in items),
            "vrs_rate": sum(bool(row["vrs"]["passed"]) for row in items) / len(items),
            "forbidden_action_runs": sum(not bool(row["outcome"]["safe"]) for row in items),
            "evidence_closed_runs": sum(bool(row["outcome"]["evidence_closed"]) for row in items),
            "evidence_closed_rate": _rate(items, "evidence_closed"),
            "safe_abstention_rate": sum(
                row["outcome"]["disposition"] == "abstained"
                and int(row["outcome"]["action_count"]) == 0
                and bool(row["vrs"]["passed"])
                for row in control
            ) / len(control),
            "median_elapsed_seconds": statistics.median(float(row["elapsed_seconds"]) for row in items),
        }
    cases: list[dict[str, Any]] = []
    for case in range(1, 16):
        case_id = f"CASE-{case:02}"
        item: dict[str, Any] = {"case_id": case_id}
        for system in ("react", "proofix"):
            case_rows = [row for row in rows if row["case_id"] == case_id and row["system"] == system]
            item[system] = {
                "vrs_passes": sum(bool(row["vrs"]["passed"]) for row in case_rows),
                "vrs_rate": sum(bool(row["vrs"]["passed"]) for row in case_rows) / 3,
                "forbidden_action_runs": sum(not bool(row["outcome"]["safe"]) for row in case_rows),
                "median_elapsed_seconds": statistics.median(
                    float(row["elapsed_seconds"]) for row in case_rows
                ),
            }
        cases.append(item)
    return {
        "schema_version": "1.0",
        "matrix": {"cases": 15, "systems": 2, "trials_per_case": 3, "valid_runs": len(rows), "pairs": 45},
        "integrity": integrity,
        "systems": systems,
        "paired_vrs": {
            "baseline_rate": paired.baseline_rate,
            "proofix_rate": paired.proofix_rate,
            "lift_percentage_points": paired.lift_percentage_points,
            "bootstrap_95_ci_percentage_points": [paired.bootstrap_ci_low, paired.bootstrap_ci_high],
            "discordant_proofix_wins": paired.discordant_proofix_wins,
            "discordant_baseline_wins": paired.discordant_baseline_wins,
            "mcnemar_exact_p": paired.mcnemar_exact_p,
            "bootstrap_samples": 10_000,
            "bootstrap_seed": 2026,
        },
        "cases": cases,
    }


def _markdown(summary: dict[str, Any]) -> str:
    paired = summary["paired_vrs"]
    systems = summary["systems"]
    lines = [
        "# Frozen benchmark results",
        "",
        f"Exactly **{summary['matrix']['valid_runs']} valid runs** form **{summary['matrix']['pairs']} paired comparisons** across 15 cases.",
        "",
        "| Metric | ReAct baseline | ProofFix | Difference |",
        "|---|---:|---:|---:|",
        f"| VRS | {paired['baseline_rate']:.1%} | {paired['proofix_rate']:.1%} | {paired['lift_percentage_points']:+.1f} pp |",
        f"| Evidence closure | {systems['react']['evidence_closed_rate']:.1%} | {systems['proofix']['evidence_closed_rate']:.1%} | {(systems['proofix']['evidence_closed_rate']-systems['react']['evidence_closed_rate'])*100:+.1f} pp |",
        f"| Forbidden-action runs | {systems['react']['forbidden_action_runs']} | {systems['proofix']['forbidden_action_runs']} | {systems['proofix']['forbidden_action_runs']-systems['react']['forbidden_action_runs']:+d} |",
        f"| Safe abstention (CASE-15) | {systems['react']['safe_abstention_rate']:.1%} | {systems['proofix']['safe_abstention_rate']:.1%} | {(systems['proofix']['safe_abstention_rate']-systems['react']['safe_abstention_rate'])*100:+.1f} pp |",
        f"| Median elapsed time | {systems['react']['median_elapsed_seconds']:.1f}s | {systems['proofix']['median_elapsed_seconds']:.1f}s | {systems['proofix']['median_elapsed_seconds']-systems['react']['median_elapsed_seconds']:+.1f}s |",
        "",
        f"Paired bootstrap 95% CI for VRS lift: **[{paired['bootstrap_95_ci_percentage_points'][0]:+.1f}, {paired['bootstrap_95_ci_percentage_points'][1]:+.1f}] pp** (10,000 resamples, seed 2026). Exact McNemar **p={paired['mcnemar_exact_p']:.6g}**; discordant pairs: ProofFix wins {paired['discordant_proofix_wins']}, baseline wins {paired['discordant_baseline_wins']}.",
        "",
        "| Case | ReAct VRS | ProofFix VRS | ReAct median | ProofFix median |",
        "|---|---:|---:|---:|---:|",
    ]
    for case in summary["cases"]:
        lines.append(
            f"| {case['case_id']} | {case['react']['vrs_rate']:.0%} ({case['react']['vrs_passes']}/3) | "
            f"{case['proofix']['vrs_rate']:.0%} ({case['proofix']['vrs_passes']}/3) | "
            f"{case['react']['median_elapsed_seconds']:.1f}s | {case['proofix']['median_elapsed_seconds']:.1f}s |"
        )
    lines.extend(
        [
            "",
            f"Integrity verification covered **{summary['integrity']['verified_trajectories']} hash-chained trajectories** and **{summary['integrity']['events']} events**.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--runs-root", type=Path, required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--invalid", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--summary-md", type=Path, required=True)
    args = parser.parse_args()
    rows = _rows(args.input)
    selected = _select_valid(rows)
    integrity = _validate_artifacts(selected, args.runs_root)
    summary = _summary(selected, integrity)
    invalid_by_id = {
        str(row["run_id"]): row for row in rows if not bool(row.get("valid")) and row.get("run_id")
    }
    for path in (args.results, args.invalid, args.summary_json, args.summary_md):
        path.parent.mkdir(parents=True, exist_ok=True)
    args.results.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in selected), encoding="utf-8"
    )
    args.invalid.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in sorted(invalid_by_id.values(), key=lambda row: str(row["run_id"]))),
        encoding="utf-8",
    )
    args.summary_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.summary_md.write_text(_markdown(summary), encoding="utf-8")
    print(json.dumps({"valid_runs": len(selected), "invalid_attempts": len(invalid_by_id), **integrity}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
