#!/usr/bin/env bash
set -euo pipefail
fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; namespace="proofix-case-13"; claim="ledger-data"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30113}"; storage_class="${PROOFIX_CASE13_STORAGE_CLASS:-local-path}"
require_tools() { command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 2; }; command -v python3 >/dev/null || exit 2; kubectl version --request-timeout=10s >/dev/null; }
ready_nodes() {
  kubectl get nodes --no-headers \
    -o 'custom-columns=NAME:.metadata.name,READY:.status.conditions[?(@.type=="Ready")].status' \
    | awk '$2 == "True" {print $1}' | sort
}
run_load() {
  kubectl port-forward -n "${namespace}" service/ledger-api 30113:80 \
    >"${TMPDIR:-/tmp}/proofix-case13-port-forward.log" 2>&1 &
  forward_pid=$!
  trap 'kill "${forward_pid}" 2>/dev/null || true' RETURN
  for _ in $(seq 1 60); do
    if python3 -c 'import socket; s=socket.create_connection(("127.0.0.1",30113),.2); s.close()' \
      >/dev/null 2>&1; then break; fi
    sleep 0.5
  done
  python3 "${fixture_dir}/load.py" --base-url "${base_url}"
  kill "${forward_pid}" 2>/dev/null || true
  wait "${forward_pid}" 2>/dev/null || true
  trap - RETURN
}
