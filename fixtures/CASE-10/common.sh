#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-10"
billing_deployment="billing-api"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30080}"

require_tools() {
  command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 2; }
  command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 2; }
  command -v base64 >/dev/null || { echo "base64 is required" >&2; exit 2; }
  command -v sha256sum >/dev/null || { echo "sha256sum is required" >&2; exit 2; }
  command -v curl >/dev/null || { echo "curl is required" >&2; exit 2; }
  kubectl version --request-timeout=10s >/dev/null
}

create_secret_from_file() {
  local secret_name="$1"
  local password_file="$2"
  kubectl create secret generic "${secret_name}" -n "${namespace}" \
    --from-file=password="${password_file}" \
    --dry-run=client -o yaml | kubectl apply -f - >/dev/null
}

secret_to_file() {
  local secret_name="$1"
  local output_file="$2"
  umask 077
  kubectl get secret "${secret_name}" -n "${namespace}" \
    -o jsonpath='{.data.password}' | base64 -d >"${output_file}"
}

secret_hash() {
  kubectl get secret "$1" -n "${namespace}" \
    -o jsonpath='{.data.password}' | base64 -d | sha256sum | awk '{print $1}'
}

secret_version() {
  kubectl get secret "$1" -n "${namespace}" -o jsonpath='{.metadata.resourceVersion}'
}

wait_for_workloads() {
  wait_for_deployment postgres
  wait_for_deployment "${billing_deployment}"
  for _ in $(seq 1 180); do
    pod_count="$(kubectl get pods -n "${namespace}" \
      -l app.kubernetes.io/name=billing-api --no-headers | wc -l)"
    if [[ "${pod_count}" == "1" ]]; then
      break
    fi
    sleep 1
  done
  [[ "${pod_count}" == "1" ]] || {
    echo "old billing-api pod did not finish terminating" >&2
    return 1
  }
  consecutive=0
  for attempt in $(seq 1 120); do
    if curl -fsS --max-time 1 "${base_url}/healthz" >/dev/null; then
      consecutive=$((consecutive + 1))
      if (( consecutive >= 5 )); then return 0; fi
    else
      consecutive=0
    fi
    sleep 0.5
  done
  echo "billing-api NodePort did not become reachable" >&2
  return 1
}

wait_for_deployment() {
  local name="$1"
  for _ in $(seq 1 180); do
    if kubectl rollout status deployment/"${name}" -n "${namespace}" \
      --watch=false >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "deployment/${name} did not complete its rollout" >&2
  return 1
}

roll_billing_for_secret_version() {
  local version
  version="$(secret_version billing-credentials)"
  kubectl patch deployment "${billing_deployment}" -n "${namespace}" --type merge \
    -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"proofix.io/billing-secret-resource-version\":\"${version}\"}}}}}" >/dev/null
  wait_for_deployment "${billing_deployment}"
}

run_current_credential_probe() {
  kubectl delete job probe-current-db-credential -n "${namespace}" --ignore-not-found >/dev/null
  kubectl apply -f "${fixture_dir}/probe-job.yaml" >/dev/null
  kubectl wait --for=condition=complete job/probe-current-db-credential \
    -n "${namespace}" --timeout=90s >/dev/null
  kubectl logs job/probe-current-db-credential -n "${namespace}"
}
