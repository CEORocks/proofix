#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-14"; claim="uploads"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30114}"
good_storage_class="${PROOFIX_GOOD_STORAGE_CLASS:-local-path}"
require_tools() { command -v kubectl >/dev/null || { echo "kubectl is required" >&2; exit 2; }; kubectl version --request-timeout=10s >/dev/null; }

assert_unbound_empty_benchmark_claim() {
  phase="$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.status.phase}')"
  volume="$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.spec.volumeName}')"
  owned="$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.metadata.labels.proofix\.io/benchmark-owned}')"
  expected_empty="$(kubectl get pvc "${claim}" -n "${namespace}" -o jsonpath='{.metadata.labels.proofix\.io/expected-empty}')"
  [[ "${phase}" == "Pending" && -z "${volume}" && "${owned}" == "true" && "${expected_empty}" == "true" ]] || {
    echo "refusing PVC recreation: claim is not evaluator-confirmed Pending/unbound/empty/benchmark-owned" >&2; exit 1;
  }
  mounted="$(kubectl get pods -n "${namespace}" -o jsonpath='{range .items[?(@.status.phase=="Running")]}{range .spec.volumes[?(@.persistentVolumeClaim.claimName=="uploads")]}mounted{end}{end}')"
  [[ -z "${mounted}" ]] || { echo "refusing PVC recreation: uploads is mounted by a Running pod" >&2; exit 1; }
}
