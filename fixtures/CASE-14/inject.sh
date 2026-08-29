#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
kubectl apply -f "${fixture_dir}/broken-storageclass.yaml" >/dev/null
if ! kubectl get pvc "${claim}" -n "${namespace}" >/dev/null 2>&1; then kubectl apply -f "${fixture_dir}/fault-pvc.yaml" >/dev/null; fi
class="$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.spec.storageClassName}')"
[[ "${class}" == "proofix-case14-broken-local" ]] || { echo "refusing to replace recovered/non-fault PVC; clean evaluator namespace required" >&2; exit 3; }
for _ in $(seq 1 30); do
  phase="$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.status.phase}')"
  [[ "${phase}" == "Pending" ]] && { echo "CASE-14 fault active: PVC Pending under nonexistent provisioner"; exit 0; }
  sleep 1
done
echo "PVC did not remain Pending" >&2; exit 1
