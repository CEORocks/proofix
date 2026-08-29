#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl patch service catalog-api -n "${namespace}" --type merge \
  --patch-file "${fixture_dir}/fault-patch.yaml"
"${fixture_dir}/verify.sh" fault
