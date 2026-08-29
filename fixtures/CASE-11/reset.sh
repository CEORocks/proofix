#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

kubectl scale deployment/orders-consumer -n "${namespace}" --replicas=3
kubectl rollout status deployment/orders-consumer -n "${namespace}" --timeout=180s
echo "CASE-11 recovery applied: restored three consumers without changing producer load or offsets"
