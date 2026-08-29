#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mkdir -p "${evidence_dir}"

override="$(kubectl get configmap/kafka-startup-override -n "${namespace}" -o jsonpath='{.data.extra_args}')"
if [[ "${override}" == "--proofix-invalid-startup-flag" ]]; then
  python3 "${fixture_dir}/partition_probe.py" fault --timeout 180
  python3 "${fixture_dir}/record_probe.py"
  echo "CASE-12 fault already active and verified"
  exit 0
fi

python3 "${fixture_dir}/partition_probe.py" healthy --timeout 180
counter="$(state_value run_counter)"
run=$((counter + 1))
pre_prefix="case12-run-${run}-pre"
fault_prefix="case12-run-${run}-fault"
pvc_uid="$(kubectl get pvc/data-kafka-2 -n "${namespace}" -o jsonpath='{.metadata.uid}')"
broker_id="$(kubectl exec -n "${namespace}" kafka-2 -- \
  rpk redpanda config print --host 127.0.0.1:9644 \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["node_id"])')"

set_state run_counter "${run}"
set_state pvc_uid "${pvc_uid}"
set_state broker_id "${broker_id}"
set_state pre_prefix "${pre_prefix}"
set_state fault_prefix "${fault_prefix}"

produce_markers "${pre_prefix}" 60
rpk_exec topic describe "${topic}" --print-partitions >"${evidence_dir}/run-${run}-pre-partitions.txt"
kubectl get pvc/data-kafka-2 -n "${namespace}" -o json >"${evidence_dir}/run-${run}-pvc-before.json"

guard_run kubectl apply -f "${fixture_dir}/override-fault.yaml"
guard_run kubectl delete pod/kafka-2 -n "${namespace}" --wait=false

deadline=$((SECONDS + 180))
until [[ "$(kubectl get pod/kafka-2 -n "${namespace}" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || true)" == "false" ]] \
  && kubectl logs -n "${namespace}" kafka-2 2>&1 | grep -Eqi 'unknown flag|proofix-invalid|invalid'; do
  (( SECONDS < deadline )) || {
    echo "fault override did not produce an evidenced kafka-2 startup failure" >&2
    kubectl describe pod/kafka-2 -n "${namespace}" >&2 || true
    exit 1
  }
  sleep 5
done

python3 "${fixture_dir}/partition_probe.py" fault --timeout 180
produce_markers "${fault_prefix}" 60
rpk_exec topic describe "${topic}" --print-partitions >"${evidence_dir}/run-${run}-fault-partitions.txt"
rpk_exec cluster health >"${evidence_dir}/run-${run}-fault-health.txt" 2>&1 || true
kubectl logs -n "${namespace}" kafka-2 >"${evidence_dir}/run-${run}-kafka-2.log" 2>&1 || true
python3 "${fixture_dir}/record_probe.py"
echo "CASE-12 fault active: kafka-2 startup blocked, PVC retained, quorum writes preserved"
