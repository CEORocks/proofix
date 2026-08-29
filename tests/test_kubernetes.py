from __future__ import annotations

import json
from typing import Any

import pytest

from proofix.kubernetes import KubernetesConfig, KubernetesEnvironment


def test_registered_additional_namespace_is_in_scope() -> None:
    environment = KubernetesEnvironment(
        KubernetesConfig(
            namespace="application",
            additional_namespaces=("kube-system",),
            probe_url="http://127.0.0.1:30000/",
            workload_selector="app=example",
        )
    )

    environment._assert_namespace("application")
    environment._assert_namespace("kube-system")
    with pytest.raises(ValueError, match="outside the registered environment"):
        environment._assert_namespace("unregistered")


def test_kubectl_get_expands_comma_separated_names(monkeypatch: pytest.MonkeyPatch) -> None:
    environment = KubernetesEnvironment(
        KubernetesConfig(
            namespace="application",
            probe_url="http://127.0.0.1:30000/",
            workload_selector="app=example",
        )
    )
    captured: list[tuple[str, ...]] = []

    def fake_json(*arguments: str) -> dict[str, Any]:
        captured.append(arguments)
        return {"items": []}

    monkeypatch.setattr(environment, "_kubectl_json", fake_json)
    environment.run_test(
        {"kind": "kubectl_get", "target": "pods/old,replacement"}
    )

    assert captured == [
        ("get", "pods/old", "pods/replacement", "-n", "application")
    ]


def test_large_kubectl_json_is_parsed_before_bounded_item_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = KubernetesEnvironment(
        KubernetesConfig(
            namespace="application",
            probe_url="http://127.0.0.1:30000/",
            workload_selector="app=example",
        )
    )
    document = {
        "apiVersion": "v1",
        "kind": "List",
        "metadata": {},
        "items": [
            {
                "apiVersion": "v1",
                "kind": "Event",
                "metadata": {
                    "name": f"event-{index:03d}",
                    "creationTimestamp": f"2026-08-29T00:{index:02d}:00Z",
                },
                "message": "x" * 5_000,
            }
            for index in range(60)
        ],
    }
    encoded = json.dumps(document)
    assert len(encoded) > 200_000
    monkeypatch.setattr(environment, "_run_kubectl", lambda *_args, **_kwargs: encoded)

    result = environment._kubectl_json("get", "events")

    assert len(result["items"]) == 50
    assert result["metadata"]["proofixOriginalItemCount"] == 60
    assert result["items"][0]["metadata"]["name"] == "event-010"
