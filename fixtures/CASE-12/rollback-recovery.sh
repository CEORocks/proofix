#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

guard_run kubectl apply -f "${fixture_dir}/override-fault.yaml"
guard_run kubectl delete pod/kafka-2 -n "${namespace}" --wait=false
echo "CASE-12 recovery rolled back: bad startup override restored without touching broker storage"
