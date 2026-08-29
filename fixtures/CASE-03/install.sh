#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
kubectl patch service catalog-api -n "${namespace}" --type merge \
  --patch-file "${fixture_dir}/recovery-patch.yaml"
wait_ready
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-03 installed healthy at ${base_url}"
