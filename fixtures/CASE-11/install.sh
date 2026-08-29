#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
require_single_node_k3s

kubectl delete namespace "${namespace}" --ignore-not-found --wait=true >/dev/null
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/broker.yaml"
kubectl rollout status statefulset/redpanda -n "${namespace}" --timeout=300s

if ! rpk_exec topic list --format json | python3 -c 'import json,sys; raise SystemExit(0 if "orders" in str(json.load(sys.stdin)) else 1)'; then
  rpk_exec topic create orders --partitions 6 --replicas 1 \
    --topic-config retention.ms=86400000
fi

kubectl apply -f "${fixture_dir}/workloads.yaml"
kubectl scale deployment/orders-consumer -n "${namespace}" --replicas=3
wait_for_workloads

python3 "${fixture_dir}/lag_probe.py" recovered --timeout 240
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-11 installed healthy: six partitions, three consumers, fixed producer load"
