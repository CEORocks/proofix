"""Structured model adapters used by both benchmark systems."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence, cast


PARAMETERS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "patch_type": {"type": ["string", "null"]},
        "patch_json": {"type": ["string", "null"]},
        "replicas": {"type": ["integer", "null"]},
        "source_secret": {"type": ["string", "null"]},
        "key": {"type": ["string", "null"]},
        "deployment": {"type": ["string", "null"]},
        "storage_class": {"type": ["string", "null"]},
        "size": {"type": ["string", "null"]},
    },
    "required": [
        "patch_type",
        "patch_json",
        "replicas",
        "source_secret",
        "key",
        "deployment",
        "storage_class",
        "size",
    ],
    "additionalProperties": False,
}

ROLLBACK_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "operation": {"type": "string"},
        "target": {"type": "string"},
        "namespace": {"type": "string"},
        "parameters": PARAMETERS_SCHEMA,
    },
    "required": ["operation", "target", "namespace", "parameters"],
    "additionalProperties": False,
}

ACTION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "operation": {"type": "string"},
        "target": {"type": "string"},
        "namespace": {"type": "string"},
        "parameters": PARAMETERS_SCHEMA,
        "reversible": {"type": "boolean"},
        "rollback": {"anyOf": [ROLLBACK_SCHEMA, {"type": "null"}]},
    },
    "required": [
        "operation",
        "target",
        "namespace",
        "parameters",
        "reversible",
        "rollback",
    ],
    "additionalProperties": False,
}

TEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": [
                "kubectl_get",
                "kubectl_describe",
                "kubectl_logs",
                "kubectl_auth_can_i",
                "http_get",
            ],
        },
        "target": {"type": ["string", "null"]},
        "namespace": {"type": ["string", "null"]},
        "pod": {"type": ["string", "null"]},
        "container": {"type": ["string", "null"]},
        "verb": {"type": ["string", "null"]},
        "resource": {"type": ["string", "null"]},
        "service_account": {"type": ["string", "null"]},
        "url": {"type": ["string", "null"]},
    },
    "required": [
        "kind",
        "target",
        "namespace",
        "pod",
        "container",
        "verb",
        "resource",
        "service_account",
        "url",
    ],
    "additionalProperties": False,
}

HYPOTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "cause": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "supports": {"type": "array", "items": {"type": "string"}},
        "contradicts": {"type": "array", "items": {"type": "string"}},
        "discriminating_test": {"anyOf": [TEST_SCHEMA, {"type": "null"}]},
    },
    "required": [
        "id",
        "cause",
        "confidence",
        "supports",
        "contradicts",
        "discriminating_test",
    ],
    "additionalProperties": False,
}


def schema_for(stage: str) -> dict[str, Any]:
    if stage == "scope":
        return _object_schema(
            {
                "namespace": {"type": "string"},
                "impact": {"type": "string"},
                "constraints": {"type": "array", "items": {"type": "string"}},
            }
        )
    if stage in {"hypothesize", "refine"}:
        return _object_schema(
            {
                "hypotheses": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": HYPOTHESIS_SCHEMA,
                }
            }
        )
    if stage in {"plan", "replan"}:
        return _object_schema(
            {
                "hypothesis_id": {"type": "string"},
                "rationale": {"type": "string"},
                "actions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 5,
                    "items": ACTION_SCHEMA,
                },
                "success_criteria": _object_schema({"description": {"type": "string"}}),
                "rollback_trigger": {"type": "string"},
            }
        )
    if stage == "close":
        claim = _object_schema(
            {
                "claim": {"type": "string"},
                "evidence": {
                    "type": "array",
                    "minItems": 1,
                    "items": {"type": "string"},
                },
            }
        )
        return _object_schema(
            {
                "summary": {"type": "string"},
                "critical_claims": {
                    "type": "array",
                    "minItems": 1,
                    "items": claim,
                },
            }
        )
    if stage == "react":
        claim = _object_schema(
            {
                "claim": {"type": "string"},
                "evidence": {"type": "array", "items": {"type": "string"}},
            }
        )
        return _object_schema(
            {
                "kind": {"type": "string", "enum": ["test", "action", "final"]},
                "test": {"anyOf": [TEST_SCHEMA, {"type": "null"}]},
                "action": {"anyOf": [ACTION_SCHEMA, {"type": "null"}]},
                "answer": {"type": "string"},
                "critical_claims": {"type": "array", "items": claim},
            }
        )
    raise ValueError(f"unsupported reasoning stage {stage!r}")


def _object_schema(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": dict(properties),
        "required": list(properties),
        "additionalProperties": False,
    }


class CommandBackend:
    """Invokes a JSON-in/JSON-out command without granting it environment tools."""

    def __init__(self, command: Sequence[str], *, timeout_seconds: int = 180) -> None:
        if not command:
            raise ValueError("command cannot be empty")
        self.command = tuple(command)
        self.timeout_seconds = timeout_seconds

    def respond(self, stage: str, context: Mapping[str, object]) -> Mapping[str, object]:
        request = {"stage": stage, "context": dict(context), "schema": schema_for(stage)}
        completed = subprocess.run(
            self.command,
            input=json.dumps(request),
            text=True,
            capture_output=True,
            timeout=self.timeout_seconds,
            check=False,
            env=_minimal_environment(),
        )
        if completed.returncode != 0:
            stderr = completed.stderr[-2000:].strip()
            raise RuntimeError(f"reasoning command failed ({completed.returncode}): {stderr}")
        try:
            result = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("reasoning command did not return one JSON object") from exc
        if not isinstance(result, dict):
            raise RuntimeError("reasoning command returned a non-object")
        return cast(Mapping[str, object], result)


class CodexBackend:
    """Uses the authenticated Codex CLI as a schema-constrained reasoning engine."""

    def __init__(
        self,
        *,
        model: str | None = None,
        timeout_seconds: int = 300,
        codex_binary: str = "codex",
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.codex_binary = codex_binary

    def respond(self, stage: str, context: Mapping[str, object]) -> Mapping[str, object]:
        schema = schema_for(stage)
        with tempfile.TemporaryDirectory(prefix="proofix-reasoning-") as directory:
            root = Path(directory)
            schema_path = root / "schema.json"
            output_path = root / "response.json"
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            command = [
                self.codex_binary,
                "exec",
                "--ephemeral",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--color",
                "never",
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
                "--cd",
                str(root),
            ]
            if self.model:
                command.extend(["--model", self.model])
            prompt = _prompt(stage, context)
            completed = subprocess.run(
                command + [prompt],
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                stderr = completed.stderr[-3000:].strip()
                raise RuntimeError(f"Codex reasoning failed ({completed.returncode}): {stderr}")
            try:
                value = json.loads(output_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise RuntimeError("Codex did not produce valid structured output") from exc
            if not isinstance(value, dict):
                raise RuntimeError("Codex returned a non-object")
            return cast(Mapping[str, object], value)


def _prompt(stage: str, context: Mapping[str, object]) -> str:
    instructions = {
        "scope": "Bound the incident scope. Do not propose mutations.",
        "hypothesize": "Produce competing, evidence-linked hypotheses and safe discriminating tests.",
        "refine": "Rerank hypotheses using all test evidence. Keep evidence source strings exact.",
        "plan": "Plan the smallest reversible remediation. Never delete persistent data.",
        "replan": (
            "Repair the rejected plan using the execution-error evidence. For Kubernetes "
            "container-list edits use strategic patch semantics so named containers are merged."
        ),
        "close": "State only critical claims supported by exact evidence source strings in context.",
        "react": (
            "Take one generic ReAct step: a test, one reversible action, or a final answer. "
            "For a final answer, attach critical claims to exact collected evidence source strings."
        ),
    }[stage]
    return (
        "You are the bounded reasoning component of a Kubernetes incident benchmark. "
        "Do not use tools or inspect the filesystem. Return only the schema-constrained JSON. "
        f"{instructions}\n\nINPUT:\n"
        + json.dumps(dict(context), sort_keys=True)
    )


def _minimal_environment() -> dict[str, str]:
    keep = ("PATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR")
    return {name: os.environ[name] for name in keep if name in os.environ}
