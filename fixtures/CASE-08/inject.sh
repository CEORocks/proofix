#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl patch deployment "${deployment}" -n "${namespace}" --type strategic \
  --patch-file "${fixture_dir}/fault-patch.yaml"
kubectl rollout status "deployment/${deployment}" -n "${namespace}" --timeout=180s
kubectl wait --for=condition=Ready pod -n "${namespace}" -l "${selector}" --timeout=180s
start_transport
trap stop_transport EXIT

before_throttled="$(wait_for_cpu_stat | awk '$1 == "nr_throttled" {print $2}')"
max_throttled="${before_throttled}"
python3 "${fixture_dir}/load.py" trigger --base-url "${base_url}" \
  --duration 60 --concurrency 32 >"${TMPDIR:-/tmp}/proofix-case-08-load.json" &
load_pid=$!
trap 'kill "${load_pid}" 2>/dev/null || true; stop_transport' EXIT

deadline=$((SECONDS + 75))
observed_restarts=0
while (( SECONDS < deadline )); do
  observed_restarts="$(restart_count 2>/dev/null || echo 0)"
  current_throttled="$(cpu_stat 2>/dev/null | awk '$1 == "nr_throttled" {print $2}' || echo 0)"
  if [[ "${current_throttled}" =~ ^[0-9]+$ ]] && (( current_throttled > max_throttled )); then
    max_throttled="${current_throttled}"
  fi
  if (( observed_restarts >= 2 )); then
    break
  fi
  sleep 1
done
wait "${load_pid}" || true
trap stop_transport EXIT
cat "${TMPDIR:-/tmp}/proofix-case-08-load.json"

after_throttled="$(cpu_stat 2>/dev/null | awk '$1 == "nr_throttled" {print $2}' || echo 0)"
after_throttled="${after_throttled:-0}"
if (( after_throttled > max_throttled )); then max_throttled="${after_throttled}"; fi
if (( max_throttled <= 0 )); then
  echo "CPU nr_throttled did not increase under the fixed load" >&2
  exit 1
fi
if (( observed_restarts < 2 )); then
  echo "liveness restart cascade was not observed; restartCount=${observed_restarts}" >&2
  exit 1
fi
echo "CASE-08 fault active: nr_throttled increased and restartCount=${observed_restarts}"
