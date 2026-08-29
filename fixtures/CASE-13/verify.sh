#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
mode="${1:-fault}"; kubectl get pvc "${claim}" -n "${namespace}" -o json; kubectl get pods -n "${namespace}" -o wide; kubectl get volumeattachments.storage.k8s.io -o json
if [[ "${mode}" == "fault" ]]; then python3 "${fixture_dir}/storage_probe.py" support; python3 "${fixture_dir}/storage_probe.py" fault --timeout 5; exit; fi
[[ "${mode}" == "recovered" ]] || { echo "usage: $0 fault|recovered" >&2; exit 2; }
kubectl wait --for=condition=Ready pod/ledger-replacement -n "${namespace}" --timeout=10s
run_load
