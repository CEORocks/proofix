#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
python3 "${fixture_dir}/storage_probe.py" support
primary="$(kubectl get pod ledger-primary -n "${namespace}" -o jsonpath='{.spec.nodeName}')"; secondary="$(ready_nodes | grep -vx "${primary}" | head -n1)"
[[ -n "${secondary}" ]] || { echo "secondary Ready node vanished" >&2; exit 3; }
kubectl delete pod ledger-primary -n "${namespace}" --wait=false >/dev/null
sed "s/__SECONDARY_NODE__/${secondary}/g" "${fixture_dir}/replacement-pod.yaml" | kubectl apply -f -
python3 "${fixture_dir}/storage_probe.py" fault --timeout 90
