#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
kubectl patch virtualservice checkout -n proofix-case-01 --type merge \
  --patch-file "${fixture_dir}/recovery-patch.json"

for attempt in $(seq 1 30); do
  status="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 2 http://127.0.0.1:30081/ || true)"
  if [[ "${status}" == "200" ]]; then
    echo "CASE-01 reset healthy: ingress returned HTTP 200"
    exit 0
  fi
  sleep 1
done

echo "CASE-01 reset did not converge to HTTP 200" >&2
exit 1
