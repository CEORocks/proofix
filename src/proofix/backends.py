"""Structured model adapters used by both benchmark systems."""

from __future__ import annotations

import json
import os
import shutil
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


class AntigravityBackend:
    """Use the authenticated Antigravity CLI as a constrained reasoning engine."""

    def __init__(
        self,
        *,
        model: str = "gemini-3.7-flash-medium",
        timeout_seconds: int = 300,
        agy_binary: str = "agy",
    ) -> None:
        self.model = model or "gemini-3.7-flash-medium"
        self.timeout_seconds = timeout_seconds
        self.agy_binary = agy_binary

    def respond(self, stage: str, context: Mapping[str, object]) -> Mapping[str, object]:
        schema = schema_for(stage)
        command = [
            self._resolve_binary(),
            "--sandbox",
            "--disable-slash-commands",
            "--model",
            self.model,
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--print-timeout",
            f"{self.timeout_seconds}s",
            "--json-schema",
            json.dumps(schema),
        ]
        stream_input = json.dumps(
            {
                "event": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": _prompt(stage, context)}],
                },
            }
        ) + "\n"
        with tempfile.TemporaryDirectory(prefix="proofix-reasoning-") as directory:
            try:
                completed = subprocess.run(
                    command,
                    input=stream_input,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                    cwd=directory,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"Antigravity reasoning timed out after {self.timeout_seconds} seconds"
                ) from exc
            except OSError as exc:
                raise RuntimeError(
                    f"Failed to execute Antigravity binary {self.agy_binary!r}: {exc}"
                ) from exc

        if completed.returncode != 0:
            detail = completed.stderr[-3000:].strip() or completed.stdout[-1000:].strip()
            raise RuntimeError(
                f"Antigravity reasoning failed ({completed.returncode}): "
                f"{detail or 'no diagnostic output'}"
            )
        try:
            events = [
                json.loads(line)
                for line in completed.stdout.splitlines()
                if line.strip().startswith("{")
            ]
        except json.JSONDecodeError as exc:
            raise RuntimeError("Antigravity did not produce valid JSON events") from exc
        if not events:
            raise RuntimeError("Antigravity did not produce a result event")
        wrapper = events[-1]
        if isinstance(wrapper, dict) and wrapper.get("event") == "result":
            wrapper = wrapper.get("result")
        if not isinstance(wrapper, dict):
            raise RuntimeError("Antigravity returned a non-object wrapper")
        if wrapper.get("status") != "SUCCESS":
            wrapper_detail = wrapper.get("error") or wrapper.get("status")
            raise RuntimeError(
                f"Antigravity returned unsuccessful status: {wrapper_detail!r}"
            )
        if wrapper.get("structured_output") is None:
            raise RuntimeError("Antigravity wrapper missing structured_output")
        value = wrapper["structured_output"]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    "Antigravity structured_output is not valid JSON"
                ) from exc
        if not isinstance(value, dict):
            raise RuntimeError("Antigravity structured_output is not a JSON object")
        for key in schema.get("required", []):
            if key not in value:
                raise RuntimeError(
                    f"Antigravity structured_output missing required property {key!r}"
                )
        return cast(Mapping[str, object], value)

    def _resolve_binary(self) -> str:
        if "/" in self.agy_binary or Path(self.agy_binary).is_file():
            return self.agy_binary
        found = shutil.which(self.agy_binary)
        if found:
            return found
        if self.agy_binary == "agy":
            fallback = Path.home() / ".local" / "bin" / "agy"
            if fallback.is_file():
                return str(fallback)
        return self.agy_binary


def _prompt(stage: str, context: Mapping[str, object]) -> str:
    instructions = {
        "scope": "Bound the incident scope. Do not propose mutations.",
        "hypothesize": "Produce competing, evidence-linked hypotheses and safe discriminating tests.",
        "refine": "Rerank hypotheses using all test evidence. Keep evidence source strings exact.",
        "plan": "Plan the smallest reversible remediation. Never delete persistent data.",
        "replan": (
            "Repair the rejected plan using the policy-rejection or execution-error evidence. "
            "Every reversible action must include an executable rollback object. For Kubernetes "
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
