#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-05"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30075}"

require_tools() {
  command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 2; }
  command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
  command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
  kubectl version --request-timeout=10s >/dev/null
  count="$(kubectl get nodes --no-headers | wc -l | tr -d ' ')"
  [[ "${count}" == "1" ]] || { echo "CASE-05 requires exactly one k3s node" >&2; exit 2; }
}

wait_ready() {
  kubectl rollout status deployment/recommendations-api -n "${namespace}" --timeout=180s
  ready="$(kubectl get deployment recommendations-api -n "${namespace}" -o jsonpath='{.status.readyReplicas}')"
  [[ "${ready}" == "2" ]] || { echo "expected two ready replicas, got ${ready:-0}" >&2; exit 1; }
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 1 "${base_url}" >/dev/null; then
      return 0
    fi
    sleep 1
  done
  echo "recommendations-api NodePort did not become reachable" >&2
  return 1
}
