#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl patch deployment recommendations-api -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/fault-patch.yaml"
kubectl rollout status deployment/recommendations-api -n "${namespace}" --timeout=15s >/dev/null 2>&1 || true
for _ in $(seq 1 60); do
  desired="$(kubectl get deployment recommendations-api -n "${namespace}" -o jsonpath='{.spec.replicas}')"
  ready="$(kubectl get deployment recommendations-api -n "${namespace}" -o jsonpath='{.status.readyReplicas}')"
  pending="$(kubectl get pods -n "${namespace}" -l app.kubernetes.io/name=recommendations-api \
    -o jsonpath='{range .items[?(@.status.phase=="Pending")]}{.metadata.name}{"\n"}{end}')"
  [[ "${desired}" == "2" && "${ready:-0}" == "1" && -n "${pending}" ]] && {
    echo "CASE-05 fault active: one of two required replicas is Pending"; exit 0;
  }
  sleep 1
done
echo "CASE-05 did not reach the expected 1-ready/1-pending state" >&2
exit 1
