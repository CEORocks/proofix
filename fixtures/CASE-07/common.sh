#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-07"
deployment="pricing-api"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30077}"

require_tools() {
  command -v kubectl >/dev/null || {
    echo "kubectl is required" >&2
    exit 2
  }
  command -v python3 >/dev/null || {
    echo "python3 is required" >&2
    exit 2
  }
  kubectl version --request-timeout=10s >/dev/null
}

wait_for_rollout() {
  kubectl rollout status "deployment/${deployment}" -n "${namespace}" --timeout=180s
  kubectl wait --for=condition=Ready pod -n "${namespace}" \
    -l app.kubernetes.io/name=pricing-api --timeout=180s
}

