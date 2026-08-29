#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-recovered}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || { echo "usage: $0 [fault|recovered]" >&2; exit 2; }
node="$(single_node)"
echo "=== workload, scheduler, and node evidence ==="
kubectl get deployment reports-worker -n "${namespace}" -o json
kubectl get pods -n "${namespace}" -l app.kubernetes.io/name=reports-worker -o json
kubectl get events -n "${namespace}" --sort-by=.lastTimestamp -o json
kubectl get node "${node}" -o json

if [[ "${mode}" == "fault" ]]; then
  selector="$(kubectl get deployment reports-worker -n "${namespace}" -o jsonpath='{.spec.template.spec.nodeSelector.disk}')"
  tolerations="$(kubectl get deployment reports-worker -n "${namespace}" -o jsonpath='{.spec.template.spec.tolerations}')"
  [[ "${selector}" == "nvme" && -z "${tolerations}" ]] || { echo "fault pod spec is not active" >&2; exit 1; }
  node_disk="$(kubectl get node "${node}" -o jsonpath='{.metadata.labels.disk}')"
  [[ "${node_disk}" != "nvme" ]] || { echo "node unexpectedly satisfies disk=nvme" >&2; exit 1; }
  events="$(kubectl get events -n "${namespace}" --field-selector reason=FailedScheduling -o jsonpath='{range .items[*]}{.message}{"\n"}{end}')"
  grep -Eqi "taint|tolerat" <<<"${events}" || { echo "untolerated taint absent from scheduler evidence" >&2; exit 1; }
  echo "CASE-04 real nodeSelector and taint mismatch verified"
  exit 0
fi

scheduled="$(kubectl get pod -n "${namespace}" -l app.kubernetes.io/name=reports-worker -o jsonpath='{.items[0].spec.nodeName}')"
[[ "${scheduled}" == "${node}" ]] || { echo "recovered pod is not on intended node" >&2; exit 1; }
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-04 recovery and strict three-window SLO verified"
