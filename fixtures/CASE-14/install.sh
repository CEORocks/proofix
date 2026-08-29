#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"; require_tools
# Evaluator-only clean-room boundary between trials. Agents cannot invoke this
# teardown; the prior run's evidence is retained before benchmark data disposal.
kubectl delete namespace "${namespace}" --ignore-not-found --wait=true >/dev/null
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/broken-storageclass.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
if ! kubectl get pvc "${claim}" -n "${namespace}" >/dev/null 2>&1; then kubectl apply -f "${fixture_dir}/fault-pvc.yaml"; fi
echo "CASE-14 installed; use inject.sh to assert the real provisioning failure"
