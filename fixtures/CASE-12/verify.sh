#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || {
  echo "usage: $0 fault|recovered" >&2
  exit 2
}

kubectl get pod -n "${namespace}" -o wide
kubectl get pvc -n "${namespace}" -o custom-columns=NAME:.metadata.name,UID:.metadata.uid,STATUS:.status.phase,VOLUME:.spec.volumeName
rpk_exec topic describe "${topic}" --print-partitions
rpk_exec topic describe "${topic}" --print-configs
rpk_exec cluster health 2>&1 || true
kubectl get configmap/kafka-startup-override -n "${namespace}" -o yaml

if [[ "${mode}" == "fault" ]]; then
  python3 "${fixture_dir}/partition_probe.py" fault --timeout 180
  kubectl logs -n "${namespace}" kafka-2 --tail=100 2>&1 || true
  python3 "${fixture_dir}/record_probe.py"
else
  python3 "${fixture_dir}/partition_probe.py" recovered --timeout 300
  python3 "${fixture_dir}/record_probe.py"
  probe="case12-run-$(state_value run_counter)-recovered-probe"
  produce_markers "${probe}" 1
  rpk_exec topic consume "${topic}" --offset :end --format '%v\n' | grep -Fx "${probe}-0000" >/dev/null
  python3 "${fixture_dir}/load.py" --base-url "${base_url}"
fi

echo "CASE-12 ${mode} evidence verified"
