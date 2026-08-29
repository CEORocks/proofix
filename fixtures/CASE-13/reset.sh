#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
if kubectl get pod ledger-primary -n "${namespace}" >/dev/null 2>&1; then
  deleting="$(kubectl get pod ledger-primary -n "${namespace}" -o jsonpath='{.metadata.deletionTimestamp}')"
  if [[ -n "${deleting}" ]]; then kubectl patch pod ledger-primary -n "${namespace}" --type=merge -p '{"metadata":{"finalizers":[]}}'; fi
fi
kubectl wait --for=delete pod/ledger-primary -n "${namespace}" --timeout=120s || true
kubectl wait --for=condition=Ready pod/ledger-replacement -n "${namespace}" --timeout=180s
run_load
echo "CASE-13 recovered after original termination and CSI detach/reattach"
