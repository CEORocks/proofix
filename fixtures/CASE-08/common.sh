#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-08"
deployment="search-api"
selector="app.kubernetes.io/name=search-api"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:18078}"
transport_pid=""

require_tools() {
  command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 2; }
  command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
  command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
  kubectl version --request-timeout=10s >/dev/null
}

wait_for_rollout() {
  kubectl rollout status "deployment/${deployment}" -n "${namespace}" --timeout=180s
  kubectl wait --for=condition=Ready pod -n "${namespace}" -l "${selector}" --timeout=180s
}

start_transport() {
  if [[ -n "${PROOFIX_BASE_URL:-}" ]]; then
    return 0
  fi
  (
    while true; do
      kubectl port-forward -n "${namespace}" "service/${deployment}" 18078:80 \
        >>"${TMPDIR:-/tmp}/proofix-case-08-port-forward.log" 2>&1 || true
      sleep 0.2
    done
  ) &
  transport_pid=$!
}

stop_transport() {
  if [[ -n "${transport_pid}" ]]; then
    pkill -TERM -P "${transport_pid}" 2>/dev/null || true
    kill "${transport_pid}" 2>/dev/null || true
    wait "${transport_pid}" 2>/dev/null || true
  fi
}

wait_for_http() {
  required_consecutive="${1:-10}"
  consecutive=0
  for attempt in $(seq 1 360); do
    if curl -fsS --max-time 1 "${base_url}/healthz" >/dev/null; then
      consecutive=$((consecutive + 1))
      if (( consecutive >= required_consecutive )); then return 0; fi
    else
      consecutive=0
    fi
    sleep 0.5
  done
  echo "search-api transport did not become reachable" >&2
  return 1
}

restart_count() {
  kubectl get pod -n "${namespace}" -l "${selector}" \
    -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}'
}

cpu_stat() {
  kubectl exec -n "${namespace}" deployment/"${deployment}" -- cat /sys/fs/cgroup/cpu.stat
}

wait_for_cpu_stat() {
  for attempt in $(seq 1 120); do
    if stats="$(cpu_stat 2>/dev/null)"; then
      printf '%s\n' "${stats}"
      return 0
    fi
    sleep 0.5
  done
  echo "search-api container did not remain available for cgroup inspection" >&2
  return 1
}
