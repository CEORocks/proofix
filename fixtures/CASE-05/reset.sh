#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl patch deployment recommendations-api -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/recovery-patch.yaml"
wait_ready
echo "CASE-05 recovery applied: required anti-affinity changed to preferred"
