#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
require_single_node_k3s

guard_run kubectl apply -f "${fixture_dir}/namespace.yaml"
guard_run kubectl apply -f "${fixture_dir}/override-healthy.yaml"
guard_run kubectl apply -f "${fixture_dir}/cluster.yaml"

if kubectl get pod/kafka-2 -n "${namespace}" >/dev/null 2>&1; then
  override="$(kubectl get configmap/kafka-startup-override -n "${namespace}" -o jsonpath='{.data.extra_args}')"
  ready="$(kubectl get pod/kafka-2 -n "${namespace}" -o jsonpath='{.status.containerStatuses[0].ready}' 2>/dev/null || true)"
  if [[ -n "${override}" || "${ready}" != "true" ]]; then
    guard_run kubectl delete pod/kafka-2 -n "${namespace}" --wait=false
  fi
fi
wait_for_cluster

rpk_mutate cluster config set auto_create_topics_enabled false
rpk_mutate cluster config set minimum_topic_replications 3
rpk_mutate cluster config set default_topic_replications 3
rpk_mutate cluster config set write_caching_default false

if ! rpk_exec topic list --format json | python3 -c 'import json,sys; raise SystemExit(0 if "proofix-replicated" in str(json.load(sys.stdin)) else 1)'; then
  rpk_mutate topic create "${topic}" --partitions 6 --replicas 3 \
    --topic-config cleanup.policy=delete \
    --topic-config retention.ms=-1 \
    --topic-config retention.bytes=-1
fi

if ! kubectl get configmap/proofix-case12-state -n "${namespace}" >/dev/null 2>&1; then
  guard_run kubectl create configmap proofix-case12-state -n "${namespace}" \
    --from-literal=run_counter=0 --from-literal=marker_count=60 \
    --from-literal=pvc_uid=unset --from-literal=broker_id=unset \
    --from-literal=pre_prefix=unset --from-literal=fault_prefix=unset
fi

python3 "${fixture_dir}/partition_probe.py" healthy --timeout 240
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-12 installed healthy: three persistent brokers, RF=3, acks=all quorum writes"
