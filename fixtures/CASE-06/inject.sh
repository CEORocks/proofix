#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl scale deployment/checkout-api -n "${namespace}" --replicas=2
wait_checkout
kubectl scale deployment/stale-canary -n "${namespace}" --replicas=1
kubectl rollout status deployment/stale-canary -n "${namespace}" --timeout=180s
kubectl scale deployment/checkout-api -n "${namespace}" --replicas=3
for _ in $(seq 1 60); do
  events="$(kubectl get events -n "${namespace}" -o jsonpath='{range .items[*]}{.reason}{" "}{.message}{"\n"}{end}')"
  if grep -Eqi 'FailedCreate.*exceeded quota.*requests.cpu' <<<"${events}"; then
    echo "CASE-06 fault active: checkout replica admission rejected by requests.cpu quota"
    exit 0
  fi
  sleep 1
done
echo "CASE-06 did not produce the expected quota admission rejection" >&2
exit 1
