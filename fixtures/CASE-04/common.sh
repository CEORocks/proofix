#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-04"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30074}"

require_tools() {
  command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 2; }
  command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
  command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
  kubectl version --request-timeout=10s >/dev/null
}

single_node() {
  mapfile -t nodes < <(kubectl get nodes -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')
  [[ "${#nodes[@]}" -eq 1 ]] || { echo "CASE-04 requires exactly one k3s node" >&2; exit 2; }
  printf '%s\n' "${nodes[0]}"
}

wait_ready() {
  kubectl rollout status deployment/reports-worker -n "${namespace}" --timeout=180s
  kubectl wait --for=condition=Ready pod -n "${namespace}" \
    -l app.kubernetes.io/name=reports-worker --timeout=180s
  for attempt in $(seq 1 60); do
    if curl -fsS --max-time 1 "${base_url}" >/dev/null; then return 0; fi
    sleep 1
  done
  echo "reports-worker NodePort did not become reachable" >&2
  return 1
}
