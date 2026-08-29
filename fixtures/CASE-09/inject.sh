#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl apply -f "${fixture_dir}/rbac-fault.yaml"
for _ in $(seq 1 30); do
  if [[ "$(can_i get configmap/inventory-settings)" == "no" ]] && \
     python3 "${fixture_dir}/load.py" fault --base-url "${base_url}" >/dev/null; then
    echo "CASE-09 fault active: ServiceAccount receives real Kubernetes RBAC denial"
    exit 0
  fi
  sleep 1
done
echo "CASE-09 RBAC denial did not become observable" >&2
exit 1
