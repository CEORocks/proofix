#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/quota.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
kubectl scale deployment/stale-canary -n "${namespace}" --replicas=0
kubectl scale deployment/checkout-api -n "${namespace}" --replicas=2
wait_checkout
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-06 installed healthy with 200m of 500m request quota in use"
