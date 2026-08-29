#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
echo "WARNING: restoring the injected CASE-04 scheduler fault" >&2
kubectl patch deployment reports-worker -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/fault-patch.yaml"
