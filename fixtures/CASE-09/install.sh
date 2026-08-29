#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
kubectl apply -f "${fixture_dir}/rbac-recovery.yaml"
wait_for_rollout
python3 "${fixture_dir}/load.py" slo --base-url "${base_url}"
echo "CASE-09 installed with least-privilege RBAC"
