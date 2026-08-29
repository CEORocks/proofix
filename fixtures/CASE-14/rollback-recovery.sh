#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
phase="$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.status.phase}')"
if [[ "${phase}" == "Bound" ]]; then
  echo "UNSUPPORTED_SAFE_ROLLBACK: recovered PVC is bound/seeded; deleting it would violate data-loss protection" >&2
  exit 3
fi
assert_unbound_empty_benchmark_claim
kubectl delete pvc "${claim}" -n "${namespace}" --wait=true
kubectl apply -f "${fixture_dir}/fault-pvc.yaml"
echo "CASE-14 recovery rolled back while claim was still unbound and empty"
