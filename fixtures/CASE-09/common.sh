#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-09"
deployment="inventory-controller"
service_account="system:serviceaccount:${namespace}:inventory-controller"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30079}"

require_tools() {
  command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 2; }
  command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
  command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
  kubectl version --request-timeout=10s >/dev/null
}

wait_for_rollout() {
  kubectl rollout status "deployment/${deployment}" -n "${namespace}" --timeout=180s
  kubectl wait --for=condition=Ready pod -n "${namespace}" \
    -l app.kubernetes.io/name=inventory-controller --timeout=180s
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 1 "${base_url}/healthz" >/dev/null; then return 0; fi
    sleep 1
  done
  echo "inventory-controller NodePort did not become reachable" >&2
  return 1
}

can_i() {
  kubectl auth can-i "$1" "$2" -n "${namespace}" --as="${service_account}"
}
