#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
if kubectl get pod ledger-primary -n "${namespace}" >/dev/null 2>&1; then
  deleting="$(kubectl get pod ledger-primary -n "${namespace}" -o jsonpath='{.metadata.deletionTimestamp}')"
  if [[ -z "${deleting}" ]] && ! kubectl get pod ledger-replacement -n "${namespace}" >/dev/null 2>&1; then
    run_load
    echo "CASE-13 reset retained the healthy seeded primary"
    exit 0
  fi
  if [[ -n "${deleting}" ]]; then
    kubectl exec pod/ledger-primary -n "${namespace}" -- kill -TERM 1 || true
    for _ in $(seq 1 30); do
      state="$(kubectl get pod ledger-primary -n "${namespace}" \
        -o jsonpath='{.status.containerStatuses[0].state.terminated.reason}' 2>/dev/null || true)"
      [[ -n "${state}" ]] && break
      sleep 1
    done
    kubectl patch pod ledger-primary -n "${namespace}" --type=merge \
      -p '{"metadata":{"finalizers":[]}}'
    kubectl delete pod ledger-primary -n "${namespace}" --grace-period=5 --wait=false \
      >/dev/null 2>&1 || true
  fi
fi
kubectl wait --for=delete pod/ledger-primary -n "${namespace}" --timeout=120s || true
kubectl wait --for=condition=Ready pod/ledger-replacement -n "${namespace}" --timeout=180s
run_load
echo "CASE-13 recovered after original termination and CSI detach/reattach"
