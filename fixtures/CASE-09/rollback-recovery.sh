#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
echo "WARNING: restoring the CASE-09 RBAC deficit" >&2
kubectl apply -f "${fixture_dir}/rbac-fault.yaml"
