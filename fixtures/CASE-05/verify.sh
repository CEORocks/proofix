#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-recovered}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || { echo "usage: $0 [fault|recovered]" >&2; exit 2; }
echo "=== deployment, placement, scheduler, and node-capacity evidence ==="
kubectl get deployment recommendations-api -n "${namespace}" -o json
kubectl get pods -n "${namespace}" -l app.kubernetes.io/name=recommendations-api -o wide
kubectl get events -n "${namespace}" --sort-by=.lastTimestamp -o json
kubectl get nodes -o json

if [[ "${mode}" == "fault" ]]; then
  desired="$(kubectl get deployment recommendations-api -n "${namespace}" -o jsonpath='{.spec.replicas}')"
  ready="$(kubectl get deployment recommendations-api -n "${namespace}" -o jsonpath='{.status.readyReplicas}')"
  required="$(kubectl get deployment recommendations-api -n "${namespace}" \
    -o jsonpath='{.spec.template.spec.affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[0].topologyKey}')"
  [[ "${desired}" == "2" && "${ready:-0}" == "1" && "${required}" == "kubernetes.io/hostname" ]] || {
    echo "authoritative anti-affinity deadlock state absent" >&2; exit 1;
  }
  events="$(kubectl get events -n "${namespace}" --field-selector reason=FailedScheduling -o jsonpath='{range .items[*]}{.message}{"\n"}{end}')"
  grep -Eqi "anti-affinity|affinity rules" <<<"${events}" || { echo "anti-affinity scheduler evidence absent" >&2; exit 1; }
  echo "CASE-05 required pod anti-affinity deadlock verified"
  exit 0
fi

ready="$(kubectl get deployment recommendations-api -n "${namespace}" -o jsonpath='{.status.readyReplicas}')"
preferred="$(kubectl get deployment recommendations-api -n "${namespace}" \
  -o jsonpath='{.spec.template.spec.affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution[0].podAffinityTerm.topologyKey}')"
[[ "${ready}" == "2" && "${preferred}" == "kubernetes.io/hostname" ]] || { echo "safe recovery state absent" >&2; exit 1; }
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-05 recovery and strict three-window SLO verified"
