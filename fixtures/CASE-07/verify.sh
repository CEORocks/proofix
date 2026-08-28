#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

mode="${1:-recovered}"
if [[ "${mode}" != "fault" && "${mode}" != "recovered" ]]; then
  echo "usage: $0 [fault|recovered]" >&2
  exit 2
fi

echo "=== workload evidence ==="
kubectl get deployment "${deployment}" -n "${namespace}" -o json
kubectl get pods -n "${namespace}" -l app.kubernetes.io/name=pricing-api -o json
echo "=== node memory-pressure evidence ==="
kubectl get nodes -o json

args="$(kubectl get deployment "${deployment}" -n "${namespace}" \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="pricing-api")].args}')"
limit="$(kubectl get deployment "${deployment}" -n "${namespace}" \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="pricing-api")].resources.limits.memory}')"

if [[ "${limit}" != "256Mi" ]]; then
  echo "unexpected memory limit: ${limit}" >&2
  exit 1
fi

if [[ "${mode}" == "fault" ]]; then
  [[ "${args}" == *"-Xmx512m"* ]] || {
    echo "fault JVM flag -Xmx512m is absent" >&2
    exit 1
  }
  evidence="$(kubectl get pods -n "${namespace}" \
    -l app.kubernetes.io/name=pricing-api \
    -o jsonpath='{range .items[*]}{.status.containerStatuses[0].lastState.terminated.reason}{" "}{.status.containerStatuses[0].lastState.terminated.exitCode}{"\n"}{end}')"
  grep -q '^OOMKilled 137$' <<<"${evidence}" || {
    echo "no OOMKilled/137 last state found" >&2
    exit 1
  }
  echo "CASE-07 fault evidence verified"
  exit 0
fi

[[ "${args}" == *"-Xmx128m"* ]] || {
  echo "recovery JVM flag -Xmx128m is absent" >&2
  exit 1
}

before="$(kubectl get pod -n "${namespace}" -l app.kubernetes.io/name=pricing-api \
  -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')"
python3 "${fixture_dir}/load.py" slo --base-url "${base_url}" --requests 250
after="$(kubectl get pod -n "${namespace}" -l app.kubernetes.io/name=pricing-api \
  -o jsonpath='{.items[0].status.containerStatuses[0].restartCount}')"
if [[ "${before}" != "${after}" ]]; then
  echo "container restarted during post-recovery SLO verification" >&2
  exit 1
fi
echo "CASE-07 recovery and strict three-window SLO verified"

