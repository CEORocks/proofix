#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
provisioner="$(kubectl get storageclass "${good_storage_class}" -o jsonpath='{.provisioner}')"
[[ -n "${provisioner}" && "${provisioner}" != "proofix.invalid/no-such-provisioner" ]] || { echo "known-good StorageClass is absent or invalid" >&2; exit 1; }
class="$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.spec.storageClassName}')"
if [[ "${class}" == "proofix-case14-broken-local" ]]; then
  assert_unbound_empty_benchmark_claim
  kubectl delete pvc "${claim}" -n "${namespace}" --wait=true
  sed "s/__GOOD_STORAGE_CLASS__/${good_storage_class}/g" "${fixture_dir}/recovery-pvc.yaml" | kubectl apply -f -
elif [[ "${class}" != "${good_storage_class}" ]]; then
  echo "refusing recovery of unexpected StorageClass ${class}" >&2; exit 1
fi
kubectl wait --for=jsonpath='{.status.phase}'=Bound pvc/"${claim}" -n "${namespace}" --timeout=180s
kubectl rollout status deployment/uploads-api -n "${namespace}" --timeout=180s
python3 - "${base_url}" <<'PY'
import sys, urllib.request
with urllib.request.urlopen(sys.argv[1].rstrip('/') + '/seed', timeout=2) as response: assert response.status == 200
PY
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-14 safely recovered using ${good_storage_class}; evaluator seed persisted"
