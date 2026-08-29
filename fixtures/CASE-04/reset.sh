#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl patch deployment reports-worker -n "${namespace}" --type merge \
  --patch-file "${fixture_dir}/recovery-patch.yaml"
wait_ready
echo "CASE-04 recovery applied: storage=nvme plus dedicated=reports toleration"
