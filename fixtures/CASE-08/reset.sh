#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl patch deployment "${deployment}" -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/recovery-patch.yaml"
wait_for_rollout
start_transport
trap stop_transport EXIT
wait_for_http
echo "CASE-08 recovery applied: two-CPU request and three-CPU limit"
