#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
mode="${1:-fault}"; kubectl get pvc "${claim}" -n "${namespace}" -o json; kubectl get events -n "${namespace}" --sort-by=.lastTimestamp
if [[ "${mode}" == "fault" ]]; then
  assert_unbound_empty_benchmark_claim
  [[ "$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.spec.storageClassName}')" == "proofix-case14-broken-local" ]]
  [[ "$(kubectl get storageclass proofix-case14-broken-local -o jsonpath='{.provisioner}')" == "proofix.invalid/no-such-provisioner" ]]
  echo "CASE-14 real Pending/unbound/empty provisioning failure verified"; exit 0
fi
[[ "${mode}" == "recovered" ]] || { echo "usage: $0 fault|recovered" >&2; exit 2; }
[[ "$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.status.phase}')" == "Bound" ]]
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-14 binding, persistence, and three SLO windows verified"
