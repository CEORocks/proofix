"""Load and validate the authoritative ProofFix benchmark case contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Mapping


class CaseValidationError(ValueError):
    """Raised when a case manifest violates the benchmark contract."""


EXPECTED_CASES: Mapping[str, tuple[str, str]] = {
    "CASE-01": ("VirtualService subset mismatch", "routing"),
    "CASE-02": ("CoreDNS latency/NXDOMAIN", "routing"),
    "CASE-03": ("Service targetPort mismatch", "routing"),
    "CASE-04": ("nodeSelector/taints mismatch", "scheduling"),
    "CASE-05": ("PodAntiAffinity deadlock", "scheduling"),
    "CASE-06": ("ResourceQuota saturation", "scheduling"),
    "CASE-07": ("Java heap OOM Exit 137", "resource"),
    "CASE-08": ("CPU throttling/liveness cascade", "resource"),
    "CASE-09": ("ServiceAccount RBAC deficit", "auth_secrets"),
    "CASE-10": ("DB password Secret desync", "auth_secrets"),
    "CASE-11": ("Kafka consumer lag", "messaging"),
    "CASE-12": ("Kafka under-replicated partition loss", "messaging"),
    "CASE-13": ("PVC Multi-Attach", "storage"),
    "CASE-14": ("StorageClass provisioning failure", "storage"),
    "CASE-15": ("Healthy distractor abstention control", "control"),
}

EXPECTED_CASE_IDS = tuple(EXPECTED_CASES)
EXPECTED_FILENAMES = frozenset(f"{case_id}.json" for case_id in EXPECTED_CASE_IDS)

REQUIRED_FIELDS = frozenset(
    {
        "id",
        "title",
        "category",
        "difficulty",
        "injected_fault",
        "affected_workload",
        "observable_signals",
        "required_evidence",
        "accepted_recoveries",
        "forbidden_actions",
        "preconditions",
        "slo",
        "challenge",
        "control",
    }
)
LIST_FIELDS = (
    "observable_signals",
    "required_evidence",
    "accepted_recoveries",
    "forbidden_actions",
    "preconditions",
)
TEXT_FIELDS = ("id", "title", "category", "difficulty", "injected_fault", "affected_workload")
ALLOWED_DIFFICULTIES = frozenset({"easy", "medium", "hard"})
EXPECTED_SLO: Mapping[str, int | float] = {
    "http_5xx_rate_lt": 0.001,
    "p95_latency_ms_lt": 200,
    "consecutive_windows": 3,
}
DATA_LOSS_PROTECTED_CASE_IDS = frozenset({"CASE-12", "CASE-13", "CASE-14"})
DATA_LOSS_PROTECTION_PREFIX = "DATA_LOSS_PROTECTION:"
ABSTENTION_PREFIX = "ABSTAIN_NO_CHANGE:"
NO_MUTATION_PREFIX = "ANY_MUTATION:"


def _fail(source: str | Path, message: str) -> CaseValidationError:
    return CaseValidationError(f"{source}: {message}")


def _object_without_duplicate_keys(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CaseValidationError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def validate_case(data: Any, source: str | Path = "<memory>") -> dict[str, Any]:
    """Validate one decoded manifest and return it with a narrowed dictionary type."""

    if not isinstance(data, dict):
        raise _fail(source, "manifest root must be a JSON object")

    actual_fields = frozenset(data)
    missing = sorted(REQUIRED_FIELDS - actual_fields)
    extra = sorted(actual_fields - REQUIRED_FIELDS)
    if missing:
        raise _fail(source, f"missing required fields: {', '.join(missing)}")
    if extra:
        raise _fail(source, f"unknown fields are not allowed: {', '.join(extra)}")

    for field in TEXT_FIELDS:
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            raise _fail(source, f"{field} must be a non-empty string")
        if value != value.strip():
            raise _fail(source, f"{field} must not have leading or trailing whitespace")

    case_id = data["id"]
    if case_id not in EXPECTED_CASES:
        raise _fail(source, f"id must be one of {', '.join(EXPECTED_CASE_IDS)}")

    expected_title, expected_category = EXPECTED_CASES[case_id]
    if data["title"] != expected_title:
        raise _fail(source, f"{case_id} title must be {expected_title!r}")
    if data["category"] != expected_category:
        raise _fail(source, f"{case_id} category must be {expected_category!r}")
    if data["difficulty"] not in ALLOWED_DIFFICULTIES:
        raise _fail(source, "difficulty must be easy, medium, or hard")

    for field in LIST_FIELDS:
        value = data[field]
        if not isinstance(value, list) or not value:
            raise _fail(source, f"{field} must be a non-empty array")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise _fail(source, f"{field} entries must be non-empty strings")
        if any(item != item.strip() for item in value):
            raise _fail(source, f"{field} entries must not have surrounding whitespace")
        if len(value) != len(set(value)):
            raise _fail(source, f"{field} entries must be unique")

    slo = data["slo"]
    if not isinstance(slo, dict):
        raise _fail(source, "slo must be an object")
    if frozenset(slo) != frozenset(EXPECTED_SLO):
        raise _fail(source, f"slo fields must be exactly {', '.join(EXPECTED_SLO)}")
    for name, expected in EXPECTED_SLO.items():
        value = slo[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _fail(source, f"slo.{name} must be numeric")
        if value != expected:
            raise _fail(source, f"slo.{name} must equal {expected}")

    for field in ("challenge", "control"):
        if not isinstance(data[field], bool):
            raise _fail(source, f"{field} must be a boolean")
    if data["challenge"] == data["control"]:
        raise _fail(source, "exactly one of challenge and control must be true")

    if case_id == "CASE-15":
        if not data["control"] or data["challenge"]:
            raise _fail(source, "CASE-15 must be the control and not a challenge")
        if not any(item.startswith(ABSTENTION_PREFIX) for item in data["accepted_recoveries"]):
            raise _fail(source, f"CASE-15 must require {ABSTENTION_PREFIX} recovery")
        if not any(item.startswith(NO_MUTATION_PREFIX) for item in data["forbidden_actions"]):
            raise _fail(source, f"CASE-15 must forbid {NO_MUTATION_PREFIX}")
    elif not data["challenge"] or data["control"]:
        raise _fail(source, f"{case_id} must be a challenge and not a control")

    if case_id in DATA_LOSS_PROTECTED_CASE_IDS and not any(
        item.startswith(DATA_LOSS_PROTECTION_PREFIX) for item in data["forbidden_actions"]
    ):
        raise _fail(
            source,
            f"{case_id} must include a {DATA_LOSS_PROTECTION_PREFIX} forbidden action",
        )

    return data


def load_case(path: str | Path) -> dict[str, Any]:
    """Decode and validate one case manifest, including filename-to-ID consistency."""

    case_path = Path(path)
    try:
        raw = case_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise CaseValidationError(f"{case_path}: manifest must be valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise CaseValidationError(f"{case_path}: unable to read manifest: {exc}") from exc

    try:
        data = json.loads(raw, object_pairs_hook=_object_without_duplicate_keys)
    except CaseValidationError as exc:
        raise _fail(case_path, str(exc)) from exc
    except json.JSONDecodeError as exc:
        raise _fail(case_path, f"invalid JSON: {exc}") from exc

    case = validate_case(data, case_path)
    expected_filename = f"{case['id']}.json"
    if case_path.name != expected_filename:
        raise _fail(case_path, f"filename must be {expected_filename}")
    return case


def default_cases_directory() -> Path:
    """Return the repository benchmark directory for a source checkout."""

    return Path(__file__).resolve().parents[2] / "benchmark" / "cases"


def load_cases(directory: str | Path | None = None) -> list[dict[str, Any]]:
    """Load the complete 15-case suite in numeric order and reject suite drift."""

    cases_directory = Path(directory) if directory is not None else default_cases_directory()
    if not cases_directory.is_dir():
        raise CaseValidationError(f"{cases_directory}: cases directory does not exist")

    files = sorted(path for path in cases_directory.iterdir() if path.suffix == ".json")
    actual_filenames = frozenset(path.name for path in files)
    missing = sorted(EXPECTED_FILENAMES - actual_filenames)
    extra = sorted(actual_filenames - EXPECTED_FILENAMES)
    if missing:
        raise CaseValidationError(
            f"{cases_directory}: missing case manifests: {', '.join(missing)}"
        )
    if extra:
        raise CaseValidationError(
            f"{cases_directory}: unexpected JSON manifests: {', '.join(extra)}"
        )

    cases = [load_case(cases_directory / filename) for filename in sorted(EXPECTED_FILENAMES)]
    ids = [case["id"] for case in cases]
    if len(ids) != len(set(ids)):
        raise CaseValidationError(f"{cases_directory}: case IDs must be unique")
    if tuple(ids) != EXPECTED_CASE_IDS:
        raise CaseValidationError(
            f"{cases_directory}: case IDs must be exactly {', '.join(EXPECTED_CASE_IDS)}"
        )
    return cases
