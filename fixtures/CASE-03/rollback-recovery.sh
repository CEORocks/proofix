#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
echo "WARNING: restoring the injected CASE-03 targetPort fault" >&2
kubectl patch service catalog-api -n "${namespace}" --type merge \
  --patch-file "${fixture_dir}/fault-patch.yaml"
