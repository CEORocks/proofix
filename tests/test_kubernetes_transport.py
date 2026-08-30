from __future__ import annotations

import http.client
from unittest.mock import patch

from proofix.kubernetes import KubernetesConfig, KubernetesEnvironment


def test_http_disconnect_is_counted_as_failed_probe() -> None:
    environment = KubernetesEnvironment(
        KubernetesConfig(
            namespace="test",
            probe_url="http://127.0.0.1:18080/healthz",
            workload_selector="app=test",
        )
    )

    with patch(
        "proofix.kubernetes.urllib.request.urlopen",
        side_effect=http.client.RemoteDisconnected("endpoint restarted"),
    ):
        status, latency_ms = environment._http_request(environment.config.probe_url)

    assert status == 0
    assert latency_ms >= 0


def test_kubectl_timeout_exceeds_rollout_deadline() -> None:
    config = KubernetesConfig(
        namespace="test",
        probe_url="http://127.0.0.1:18080/healthz",
        workload_selector="app=test",
    )

    assert config.command_timeout_seconds > 180
