#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

kubectl patch deployment "${deployment}" -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/fault-patch.yaml"
wait_for_rollout

python3 "${fixture_dir}/load.py" trigger --base-url "${base_url}" --requests 80 || true

for _ in $(seq 1 90); do
  evidence="$(kubectl get pod -n "${namespace}" \
    -l app.kubernetes.io/name=pricing-api \
    -o jsonpath='{range .items[*]}{.status.containerStatuses[0].lastState.terminated.reason}{" "}{.status.containerStatuses[0].lastState.terminated.exitCode}{"\n"}{end}')"
  if grep -q '^OOMKilled 137$' <<<"${evidence}"; then
    echo "CASE-07 fault active: real container termination recorded as OOMKilled/137"
    exit 0
  fi
  sleep 1
done

echo "CASE-07 did not produce OOMKilled/137 within 90 seconds" >&2
kubectl get pods -n "${namespace}" -o wide >&2
exit 1

