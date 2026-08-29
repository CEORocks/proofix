#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

kubectl scale deployment/orders-consumer -n "${namespace}" --replicas=1
kubectl rollout status deployment/orders-consumer -n "${namespace}" --timeout=180s
echo "CASE-11 recovery rolled back: authoritative one-replica fault restored"
