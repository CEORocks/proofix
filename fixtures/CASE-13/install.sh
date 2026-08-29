#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
# Evaluator lifecycle boundary: each paired trial gets a fresh benchmark-owned
# volume. This teardown is outside the agent action surface and follows artifact retention.
if kubectl get namespace "${namespace}" >/dev/null 2>&1; then
  while IFS= read -r pod; do
    [[ -n "${pod}" ]] || continue
    kubectl patch -n "${namespace}" "${pod}" --type=merge \
      -p '{"metadata":{"finalizers":[]}}' >/dev/null || true
    kubectl delete -n "${namespace}" "${pod}" --grace-period=1 --wait=false \
      >/dev/null 2>&1 || true
  done < <(kubectl get pods -n "${namespace}" -o name 2>/dev/null || true)
fi
kubectl delete namespace "${namespace}" --ignore-not-found --wait=true >/dev/null
kubectl apply -f "${fixture_dir}/namespace.yaml"; kubectl apply -f "${fixture_dir}/app.yaml"
if ! kubectl get pvc "${claim}" -n "${namespace}" >/dev/null 2>&1; then sed "s/__STORAGE_CLASS__/${storage_class}/g" "${fixture_dir}/pvc.yaml" | kubectl apply -f -; fi
if ! kubectl get pod ledger-primary -n "${namespace}" >/dev/null 2>&1; then
  primary="$(ready_nodes | head -n1)"; [[ -n "${primary}" ]] || { echo "no Ready node" >&2; exit 1; }
  sed "s/__PRIMARY_NODE__/${primary}/g" "${fixture_dir}/primary-pod.yaml" | kubectl apply -f -
fi
kubectl wait --for=condition=Ready pod/ledger-primary -n "${namespace}" --timeout=180s
kubectl exec -n "${namespace}" ledger-primary -- wget -qO- http://127.0.0.1:8080/seed >/dev/null
run_load
echo "CASE-13 installed with real RWO seed data"
