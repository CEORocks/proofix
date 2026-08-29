#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-recovered}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || { echo "usage: $0 [fault|recovered]" >&2; exit 2; }

limit="$(kubectl get deployment "${deployment}" -n "${namespace}" \
  -o jsonpath='{.spec.template.spec.containers[?(@.name=="search-api")].resources.limits.cpu}')"
echo "=== deployment and cgroup evidence ==="
kubectl get deployment "${deployment}" -n "${namespace}" -o json
cpu_stat 2>/dev/null || echo "cgroup unavailable while the faulted container is restarting"
echo "=== kubelet probe events ==="
kubectl get events -n "${namespace}" --field-selector involvedObject.kind=Pod -o json

if [[ "${mode}" == "fault" ]]; then
  [[ "${limit}" == "100m" ]] || { echo "expected 100m limit, got ${limit}" >&2; exit 1; }
  restarts="$(restart_count)"
  (( restarts >= 2 )) || { echo "restart cascade absent: ${restarts}" >&2; exit 1; }
  kubectl get events -n "${namespace}" -o jsonpath='{range .items[*]}{.reason}{" "}{.message}{"\n"}{end}' \
    | grep -q 'Unhealthy.*Liveness probe failed' || { echo "liveness failure event absent" >&2; exit 1; }
  echo "CASE-08 real throttling and liveness cascade verified"
  exit 0
fi

[[ "${limit}" == "3" ]] || { echo "expected three-CPU recovery limit, got ${limit}" >&2; exit 1; }
start_transport
trap stop_transport EXIT
wait_for_http
before="$(restart_count)"
python3 "${fixture_dir}/load.py" slo --base-url "${base_url}" --concurrency 16
after="$(restart_count)"
[[ "${before}" == "${after}" ]] || { echo "container restarted during recovered SLO windows" >&2; exit 1; }
echo "CASE-08 recovery and strict three-window SLO verified"
