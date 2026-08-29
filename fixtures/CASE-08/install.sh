#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl delete namespace "${namespace}" --ignore-not-found --wait=true >/dev/null
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
kubectl patch deployment "${deployment}" -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/recovery-patch.yaml"
wait_for_rollout
start_transport
trap stop_transport EXIT
wait_for_http
python3 "${fixture_dir}/load.py" slo --base-url "${base_url}" --concurrency 16
echo "CASE-08 installed healthy at ${base_url}"
