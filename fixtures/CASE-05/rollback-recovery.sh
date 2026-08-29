#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
echo "WARNING: restoring the injected CASE-05 anti-affinity deadlock" >&2
kubectl patch deployment recommendations-api -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/fault-patch.yaml"
