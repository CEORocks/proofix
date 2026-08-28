"""Contract tests for the authoritative 15-case ProofFix benchmark."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from proofix.cases import (
    ABSTENTION_PREFIX,
    DATA_LOSS_PROTECTED_CASE_IDS,
    DATA_LOSS_PROTECTION_PREFIX,
    EXPECTED_CASES,
    EXPECTED_CASE_IDS,
    EXPECTED_SLO,
    NO_MUTATION_PREFIX,
    REQUIRED_FIELDS,
    CaseValidationError,
    default_cases_directory,
    load_case,
    load_cases,
    validate_case,
)


@pytest.fixture(scope="module")
def cases() -> list[dict[str, Any]]:
    return load_cases()


def test_loads_exact_authoritative_suite(cases: list[dict[str, Any]]) -> None:
    assert len(cases) == 15
    assert tuple(case["id"] for case in cases) == EXPECTED_CASE_IDS
    assert len({case["id"] for case in cases}) == 15
    assert {path.name for path in default_cases_directory().glob("*.json")} == {
        f"{case_id}.json" for case_id in EXPECTED_CASE_IDS
    }


def test_every_manifest_has_strict_schema_and_fixed_slo(
    cases: list[dict[str, Any]],
) -> None:
    for case in cases:
        assert set(case) == REQUIRED_FIELDS
        assert case["slo"] == EXPECTED_SLO
        expected_title, expected_category = EXPECTED_CASES[str(case["id"])]
        assert case["title"] == expected_title
        assert case["category"] == expected_category


def test_challenge_control_partition_is_exact(cases: list[dict[str, Any]]) -> None:
    for case in cases[:-1]:
        assert case["challenge"] is True
        assert case["control"] is False
    control = cases[-1]
    assert control["id"] == "CASE-15"
    assert control["challenge"] is False
    assert control["control"] is True
    assert any(
        action.startswith(ABSTENTION_PREFIX)
        for action in control["accepted_recoveries"]
    )
    assert any(
        action.startswith(NO_MUTATION_PREFIX) for action in control["forbidden_actions"]
    )


def test_data_loss_cases_have_machine_checkable_protections(
    cases: list[dict[str, Any]],
) -> None:
    by_id = {case["id"]: case for case in cases}
    for case_id in DATA_LOSS_PROTECTED_CASE_IDS:
        assert any(
            action.startswith(DATA_LOSS_PROTECTION_PREFIX)
            for action in by_id[case_id]["forbidden_actions"]
        )


def _valid_case(case_id: str = "CASE-01") -> dict[str, Any]:
    return copy.deepcopy(load_case(default_cases_directory() / f"{case_id}.json"))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda case: case.pop("required_evidence"), "missing required fields"),
        (lambda case: case.update({"measured_success": True}), "unknown fields"),
        (lambda case: case.update({"title": " "}), "title must be a non-empty string"),
        (lambda case: case.update({"category": "storage"}), "category must be"),
        (lambda case: case.update({"difficulty": "extreme"}), "difficulty must be"),
        (lambda case: case.update({"observable_signals": []}), "must be a non-empty array"),
        (
            lambda case: case.update({"required_evidence": ["duplicate", "duplicate"]}),
            "entries must be unique",
        ),
        (lambda case: case.update({"slo": {"http_5xx_rate_lt": 0.001}}), "slo fields"),
        (
            lambda case: case["slo"].update({"p95_latency_ms_lt": 201}),
            "must equal 200",
        ),
        (
            lambda case: case["slo"].update({"consecutive_windows": True}),
            "must be numeric",
        ),
        (
            lambda case: case.update({"challenge": False, "control": False}),
            "exactly one",
        ),
        (lambda case: case.update({"id": "CASE-16"}), "id must be one of"),
    ],
)
def test_rejects_malformed_case_fields(
    mutate: Callable[[dict[str, Any]], object], message: str
) -> None:
    case = _valid_case()
    mutate(case)
    with pytest.raises(CaseValidationError, match=message):
        validate_case(case)


def test_rejects_control_without_abstention() -> None:
    case = _valid_case("CASE-15")
    case["accepted_recoveries"] = ["Restart the healthy workload."]
    with pytest.raises(CaseValidationError, match=ABSTENTION_PREFIX):
        validate_case(case)


def test_rejects_control_without_no_mutation_guard() -> None:
    case = _valid_case("CASE-15")
    case["forbidden_actions"] = ["Do not trust stale logs."]
    with pytest.raises(CaseValidationError, match=NO_MUTATION_PREFIX):
        validate_case(case)


@pytest.mark.parametrize("case_id", sorted(DATA_LOSS_PROTECTED_CASE_IDS))
def test_rejects_missing_data_loss_protection(case_id: str) -> None:
    case = _valid_case(case_id)
    case["forbidden_actions"] = ["Do not make an unsafe change."]
    with pytest.raises(CaseValidationError, match=DATA_LOSS_PROTECTION_PREFIX):
        validate_case(case)


def test_rejects_filename_id_mismatch(tmp_path: Path) -> None:
    source = default_cases_directory() / "CASE-01.json"
    wrong_name = tmp_path / "CASE-02.json"
    shutil.copyfile(source, wrong_name)
    with pytest.raises(CaseValidationError, match="filename must be CASE-01.json"):
        load_case(wrong_name)


def test_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    path = tmp_path / "CASE-01.json"
    path.write_text('{"id": "CASE-01", "id": "CASE-01"}', encoding="utf-8")
    with pytest.raises(CaseValidationError, match="duplicate JSON key"):
        load_case(path)


def test_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "CASE-01.json"
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(CaseValidationError, match="invalid JSON"):
        load_case(path)


def test_rejects_incomplete_or_extra_suite(tmp_path: Path) -> None:
    suite = tmp_path / "cases"
    shutil.copytree(default_cases_directory(), suite)
    (suite / "CASE-15.json").unlink()
    with pytest.raises(CaseValidationError, match="missing case manifests: CASE-15.json"):
        load_cases(suite)

    shutil.copyfile(suite / "CASE-01.json", suite / "CASE-99.json")
    with pytest.raises(CaseValidationError, match="missing case manifests: CASE-15.json"):
        load_cases(suite)

    shutil.copyfile(default_cases_directory() / "CASE-15.json", suite / "CASE-15.json")
    with pytest.raises(CaseValidationError, match="unexpected JSON manifests: CASE-99.json"):
        load_cases(suite)


def test_manifests_round_trip_as_utf8_json(cases: list[dict[str, Any]]) -> None:
    for case in cases:
        path = default_cases_directory() / f"{case['id']}.json"
        assert json.loads(path.read_text(encoding="utf-8")) == case
