#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
echo "WARNING: restoring the CASE-08 100m CPU fault" >&2
kubectl patch deployment "${deployment}" -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/rollback-recovery-patch.yaml"
wait_for_rollout
