#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

kubectl get deployment/orders-producer -n "${namespace}" >/dev/null
kubectl scale deployment/orders-consumer -n "${namespace}" --replicas=1
kubectl rollout status deployment/orders-consumer -n "${namespace}" --timeout=180s

desired="$(kubectl get deployment/orders-consumer -n "${namespace}" -o jsonpath='{.spec.replicas}')"
[[ "${desired}" == "1" ]] || { echo "fault injection did not set one consumer" >&2; exit 1; }
echo "CASE-11 fault active: one consumer; producer remains at the fixed 42 records/second"
