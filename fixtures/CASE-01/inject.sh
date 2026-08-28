#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
kubectl patch virtualservice checkout -n proofix-case-01 --type merge \
  --patch-file "${fixture_dir}/fault-patch.json"

for attempt in $(seq 1 30); do
  status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:30081/ || true)"
  if [[ "${status}" == "503" ]]; then
    echo "CASE-01 fault active: ingress returned HTTP 503"
    exit 0
  fi
  sleep 1
done

echo "CASE-01 fault did not converge to HTTP 503" >&2
exit 1
