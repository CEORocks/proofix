#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
node="$(single_node)"
kubectl label node "${node}" storage=nvme proofix.io/case04-owned=true --overwrite
kubectl taint node "${node}" dedicated=reports:NoSchedule --overwrite
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
kubectl patch deployment reports-worker -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/recovery-patch.yaml"
wait_ready
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-04 installed healthy on intended node ${node}"
