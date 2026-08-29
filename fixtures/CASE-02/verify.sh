#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

mode="${1:-recovered}"
if [[ "${mode}" != "fault" && "${mode}" != "recovered" ]]; then
  echo "usage: $0 [fault|recovered]" >&2
  exit 2
fi

echo "=== isolated CoreDNS configuration evidence ==="
kubectl get configmap/coredns -n kube-system -o json
echo "=== CoreDNS and fixture workload evidence ==="
kubectl get pods -n kube-system -l k8s-app=kube-dns -o json
kubectl get deployment,service,pods -n "${namespace}" -o json
echo "=== isolated-zone live query evidence ==="
python3 "${fixture_dir}/load.py" dns --base-url "${base_url}" --expect "${mode}"
echo "=== unaffected general cluster DNS evidence ==="
verify_general_dns

if [[ "${mode}" == "fault" ]]; then
  python3 "${fixture_dir}/load.py" incident --base-url "${base_url}"
  echo "CASE-02 delayed NXDOMAIN incident verified without general DNS damage"
  exit 0
fi

python3 "${fixture_dir}/load.py" slo --base-url "${base_url}" --requests 250
echo "CASE-02 recovery and strict three-window SLO verified"

