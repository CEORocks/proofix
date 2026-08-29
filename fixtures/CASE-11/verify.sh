#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
mode="${1:-}"
[[ "${mode}" == "fault" || "${mode}" == "recovered" ]] || {
  echo "usage: $0 fault|recovered" >&2
  exit 2
}

kubectl get deployment/orders-producer deployment/orders-consumer -n "${namespace}" -o wide
kubectl get pods -n "${namespace}" -o wide
rpk_exec topic describe orders --print-partitions
health="$(rpk_exec cluster health 2>&1 || true)"
printf '%s\n' "${health}"
grep -Eq 'Under-replicated partitions \(0\)' <<<"${health}" || {
  echo "broker/topic health is not isolated from the consumer-lag fault" >&2
  exit 1
}
kubectl logs -n "${namespace}" deployment/orders-producer --tail=20

if [[ "${mode}" == "fault" ]]; then
  python3 "${fixture_dir}/lag_probe.py" fault
else
  python3 "${fixture_dir}/lag_probe.py" recovered --timeout 240
  python3 "${fixture_dir}/load.py" --base-url "${base_url}"
fi

echo "CASE-11 ${mode} evidence verified"
