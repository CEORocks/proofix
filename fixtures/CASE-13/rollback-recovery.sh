#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
primary="${PROOFIX_CASE13_PRIMARY_NODE:-}"; [[ -n "${primary}" ]] || { echo "PROOFIX_CASE13_PRIMARY_NODE is required for rollback" >&2; exit 2; }
kubectl delete pod ledger-replacement -n "${namespace}" --wait=true
sed "s/__PRIMARY_NODE__/${primary}/g" "${fixture_dir}/primary-pod.yaml" | kubectl apply -f -
kubectl wait --for=condition=Ready pod/ledger-primary -n "${namespace}" --timeout=180s
run_load
echo "CASE-13 recovery rolled back by safe detach then reattach; data preserved"
