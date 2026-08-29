#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-recovered}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || { echo "usage: $0 [fault|recovered]" >&2; exit 2; }

db_hash="$(secret_hash db-credentials)"
billing_hash="$(secret_hash billing-credentials)"
db_rv="$(secret_version db-credentials)"
billing_rv="$(secret_version billing-credentials)"
pod_recorded_rv="$(kubectl get deployment "${billing_deployment}" -n "${namespace}" \
  -o jsonpath='{.spec.template.metadata.annotations.proofix\.io/billing-secret-resource-version}')"
echo "db_generation_sha256=${db_hash} db_secret_rv=${db_rv}"
echo "billing_generation_sha256=${billing_hash} billing_secret_rv=${billing_rv} pod_recorded_billing_rv=${pod_recorded_rv}"
echo "=== secret references and pod metadata (no Secret data) ==="
kubectl get deployment postgres -n "${namespace}" \
  -o jsonpath='{.metadata.name}{" secretRef="}{.spec.template.spec.containers[0].env[?(@.name=="POSTGRES_PASSWORD")].valueFrom.secretKeyRef.name}{" podTemplateGeneration="}{.metadata.generation}{"\n"}'
kubectl get deployment "${billing_deployment}" -n "${namespace}" \
  -o jsonpath='{.metadata.name}{" secretRef="}{.spec.template.spec.containers[?(@.name=="db-auth-checker")].env[?(@.name=="PGPASSWORD")].valueFrom.secretKeyRef.name}{" podTemplateGeneration="}{.metadata.generation}{"\n"}'
run_current_credential_probe

if [[ "${mode}" == "fault" ]]; then
  [[ "${db_hash}" != "${billing_hash}" ]] || { echo "credential generations are unexpectedly synchronized" >&2; exit 1; }
  python3 "${fixture_dir}/load.py" fault --base-url "${base_url}"
  echo "CASE-10 live database acceptance and stale application rejection verified"
  exit 0
fi

[[ "${db_hash}" == "${billing_hash}" ]] || { echo "credential generations remain desynchronized" >&2; exit 1; }
[[ "${billing_rv}" == "${pod_recorded_rv}" ]] || { echo "billing pod template does not record current Secret version" >&2; exit 1; }
python3 "${fixture_dir}/load.py" slo --base-url "${base_url}"
echo "CASE-10 safe synchronization and strict three-window SLO verified"
