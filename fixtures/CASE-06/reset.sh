#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl scale deployment/stale-canary -n "${namespace}" --replicas=0
kubectl scale deployment/checkout-api -n "${namespace}" --replicas=3
wait_checkout
echo "CASE-06 recovery applied: benchmark-owned zero-traffic canary scaled to zero"
