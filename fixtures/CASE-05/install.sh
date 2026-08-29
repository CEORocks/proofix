#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
kubectl patch deployment recommendations-api -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/recovery-patch.yaml"
wait_ready
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-05 installed healthy with two replicas"
