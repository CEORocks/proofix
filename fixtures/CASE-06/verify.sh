#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-recovered}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || { echo "usage: $0 [fault|recovered]" >&2; exit 2; }
echo "=== quota, ownership, admission, workload, and node evidence ==="
kubectl get resourcequota case-06-cpu-budget -n "${namespace}" -o json
kubectl get deployments -n "${namespace}" -o json
kubectl get pods -n "${namespace}" -o json
kubectl get events -n "${namespace}" --sort-by=.lastTimestamp -o json
kubectl get nodes -o json

hard="$(kubectl get resourcequota case-06-cpu-budget -n "${namespace}" -o jsonpath='{.status.hard.requests\.cpu}')"
used="$(kubectl get resourcequota case-06-cpu-budget -n "${namespace}" -o jsonpath='{.status.used.requests\.cpu}')"
[[ "${hard}" == "500m" ]] || { echo "quota hard limit changed: ${hard}" >&2; exit 1; }

if [[ "${mode}" == "fault" ]]; then
  desired="$(kubectl get deployment checkout-api -n "${namespace}" -o jsonpath='{.spec.replicas}')"
  ready="$(kubectl get deployment checkout-api -n "${namespace}" -o jsonpath='{.status.readyReplicas}')"
  canary="$(kubectl get deployment stale-canary -n "${namespace}" -o jsonpath='{.spec.replicas}')"
  owner="$(kubectl get deployment stale-canary -n "${namespace}" -o jsonpath='{.metadata.labels.proofix\.io/benchmark-owned}')"
  traffic="$(kubectl get deployment stale-canary -n "${namespace}" -o jsonpath='{.metadata.labels.proofix\.io/live-traffic}')"
  [[ "${used}" == "500m" && "${desired}" == "3" && "${ready}" == "2" && "${canary}" == "1" ]] || {
    echo "quota saturation state absent (used=${used}, desired=${desired}, ready=${ready}, canary=${canary})" >&2; exit 1;
  }
  [[ "${owner}" == "true" && "${traffic}" == "false" ]] || { echo "canary ownership/zero-traffic evidence absent" >&2; exit 1; }
  events="$(kubectl get events -n "${namespace}" -o jsonpath='{range .items[*]}{.reason}{" "}{.message}{"\n"}{end}')"
  grep -Eqi 'FailedCreate.*exceeded quota.*requests.cpu' <<<"${events}" || { echo "quota admission event absent" >&2; exit 1; }
  echo "CASE-06 real ResourceQuota saturation verified"
  exit 0
fi

ready="$(kubectl get deployment checkout-api -n "${namespace}" -o jsonpath='{.status.readyReplicas}')"
canary="$(kubectl get deployment stale-canary -n "${namespace}" -o jsonpath='{.spec.replicas}')"
[[ "${ready}" == "3" && "${canary}" == "0" ]] || { echo "safe recovery state absent" >&2; exit 1; }
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-06 recovery and strict three-window SLO verified"
