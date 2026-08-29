#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-recovered}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || { echo "usage: $0 [fault|recovered]" >&2; exit 2; }

echo "=== identity and effective RBAC evidence ==="
kubectl get pod -n "${namespace}" -l app.kubernetes.io/name=inventory-controller \
  -o jsonpath='{range .items[*]}{.metadata.name}{" serviceAccount="}{.spec.serviceAccountName}{" uid="}{.metadata.uid}{"\n"}{end}'
kubectl get role inventory-settings-reader -n "${namespace}" -o yaml
kubectl get rolebinding inventory-settings-reader -n "${namespace}" -o yaml
get_result="$(can_i get configmap/inventory-settings || true)"
list_result="$(can_i list configmaps || true)"
secret_result="$(can_i get secrets || true)"
echo "can-i get configmap/inventory-settings: ${get_result}"
echo "can-i list configmaps: ${list_result}"
echo "can-i get secrets: ${secret_result}"

if [[ "${mode}" == "fault" ]]; then
  [[ "${get_result}" == "no" && "${list_result}" == "no" ]] || { echo "fault RBAC unexpectedly permits ConfigMaps" >&2; exit 1; }
  python3 "${fixture_dir}/load.py" fault --base-url "${base_url}"
  echo "CASE-09 Forbidden response and permission deficit verified"
  exit 0
fi

[[ "${get_result}" == "yes" && "${list_result}" == "yes" ]] || { echo "required ConfigMap permissions absent" >&2; exit 1; }
[[ "${secret_result}" == "no" ]] || { echo "recovery improperly grants Secret access" >&2; exit 1; }
python3 "${fixture_dir}/load.py" slo --base-url "${base_url}"
echo "CASE-09 least-privilege recovery and strict three-window SLO verified"
