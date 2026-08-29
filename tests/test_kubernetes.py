from __future__ import annotations

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
