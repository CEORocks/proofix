#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-recovered}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || { echo "usage: $0 [fault|recovered]" >&2; exit 2; }

echo "=== Service, EndpointSlice, and pod evidence ==="
kubectl get service catalog-api -n "${namespace}" -o json
kubectl get endpointslice -n "${namespace}" -l kubernetes.io/service-name=catalog-api -o json
kubectl get pods -n "${namespace}" -l app.kubernetes.io/name=catalog-api -o json
target_port="$(kubectl get service catalog-api -n "${namespace}" -o jsonpath='{.spec.ports[0].targetPort}')"
pod="$(kubectl get pod -n "${namespace}" -l app.kubernetes.io/name=catalog-api -o jsonpath='{.items[0].metadata.name}')"
direct="$(kubectl exec -n "${namespace}" "${pod}" -- wget -qO- http://127.0.0.1:8081/healthz)"
[[ "${direct}" == *healthy* ]] || { echo "direct pod port 8081 is not healthy" >&2; exit 1; }

if [[ "${mode}" == "fault" ]]; then
  [[ "${target_port}" == "8080" ]] || { echo "fault targetPort is ${target_port}, expected 8080" >&2; exit 1; }
  if python3 "${fixture_dir}/load.py" --base-url "${base_url}" --windows 1 --requests 20; then
    echo "faulted Service unexpectedly passed HTTP verification" >&2
    exit 1
  fi
  echo "CASE-03 fault verified: selected pods answer on 8081 while Service targets 8080"
  exit 0
fi

[[ "${target_port}" == "catalog-http" ]] || { echo "recovery targetPort is ${target_port}" >&2; exit 1; }
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-03 recovery and strict three-window SLO verified"
