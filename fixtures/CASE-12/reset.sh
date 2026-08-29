#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

guard_run kubectl apply -f "${fixture_dir}/override-healthy.yaml"
ready="$(kubectl get pod/kafka-2 -n "${namespace}" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || true)"
if [[ "${ready}" != "true" ]]; then
  guard_run kubectl delete pod/kafka-2 -n "${namespace}" --wait=false
fi
wait_for_cluster
echo "CASE-12 recovery applied: kafka-2 restarted on its existing retained PVC"
