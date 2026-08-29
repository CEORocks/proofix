#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
node="$(single_node)"
kubectl delete namespace "${namespace}" --ignore-not-found --wait=true
kubectl taint node "${node}" dedicated=reports:NoSchedule- >/dev/null 2>&1 || true
kubectl label node "${node}" storage- proofix.io/case04-owned- >/dev/null 2>&1 || true
echo "CASE-04 benchmark-owned node taint and labels removed"
