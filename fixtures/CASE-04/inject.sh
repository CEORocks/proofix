#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl patch deployment reports-worker -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/fault-patch.yaml"
kubectl rollout status deployment/reports-worker -n "${namespace}" --timeout=15s >/dev/null 2>&1 || true
for _ in $(seq 1 60); do
  pending="$(kubectl get pods -n "${namespace}" -l app.kubernetes.io/name=reports-worker \
    -o jsonpath='{range .items[?(@.status.phase=="Pending")]}{.metadata.name}{"\n"}{end}')"
  if [[ -n "${pending}" ]]; then
    for event_attempt in $(seq 1 20); do
      events="$(kubectl get events -n "${namespace}" --field-selector reason=FailedScheduling \
        -o jsonpath='{range .items[*]}{.message}{"\n"}{end}')"
      if [[ -n "${events}" ]]; then
        echo "CASE-04 fault active: reports-worker is Pending with FailedScheduling evidence"
        exit 0
      fi
      sleep 1
    done
    echo "Pending pod has no FailedScheduling event" >&2
    exit 1
  fi
  sleep 1
done
echo "CASE-04 did not produce a Pending pod" >&2
exit 1
