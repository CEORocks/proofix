#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-12"
topic="proofix-replicated"
brokers="kafka-0.kafka.proofix-case-12.svc.cluster.local:9092,kafka-1.kafka.proofix-case-12.svc.cluster.local:9092,kafka-2.kafka.proofix-case-12.svc.cluster.local:9092"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30082}"
evidence_dir="${PROOFIX_EVIDENCE_DIR:-/tmp/proofix-case-12-evidence}"

guard_run() {
  "${fixture_dir}/safety-guard.sh" -- "$@"
}

require_tools() {
  command -v kubectl >/dev/null || { echo "UNSUPPORTED: kubectl is required" >&2; exit 2; }
  command -v python3 >/dev/null || { echo "UNSUPPORTED: python3 is required" >&2; exit 2; }
  kubectl version --request-timeout=10s -o json >/dev/null || {
    echo "UNSUPPORTED: no reachable Kubernetes API" >&2
    exit 2
  }
}

require_single_node_k3s() {
  local version nodes storage
  version="$(kubectl version -o json | python3 -c 'import json,sys; print(json.load(sys.stdin)["serverVersion"]["gitVersion"])')"
  [[ "${version}" == *k3s* ]] || {
    echo "UNSUPPORTED: CASE-12 is preregistered for k3s; server is ${version}" >&2
    exit 3
  }
  nodes="$(kubectl get nodes --no-headers | wc -l | tr -d ' ')"
  [[ "${nodes}" == "1" ]] || {
    echo "UNSUPPORTED: CASE-12 requires exactly one k3s node; found ${nodes}" >&2
    exit 3
  }
  storage="$(kubectl get storageclass local-path -o jsonpath='{.metadata.name}' 2>/dev/null || true)"
  [[ "${storage}" == "local-path" ]] || {
    echo "UNSUPPORTED: k3s local-path StorageClass is required" >&2
    exit 3
  }
  kubectl get nodes -o json | python3 -c '
import json, re, sys
n=json.load(sys.stdin)["items"][0]
cpu_raw=n["status"]["allocatable"]["cpu"]
cpu=float(cpu_raw[:-1])/1000 if cpu_raw.endswith("m") else float(cpu_raw)
raw=n["status"]["allocatable"]["memory"]
m=re.fullmatch(r"([0-9]+)Ki", raw)
memory=int(m.group(1))*1024 if m else 0
if cpu < 4 or memory < 6*1024**3:
    raise SystemExit("UNSUPPORTED: CASE-12 requires >=4 allocatable CPU and >=6 GiB memory")
'
}

rpk_exec() {
  kubectl exec -n "${namespace}" kafka-0 -- rpk "$@" -X "brokers=${brokers}"
}

rpk_mutate() {
  guard_run kubectl exec -n "${namespace}" kafka-0 -- rpk "$@" -X "brokers=${brokers}"
}

state_value() {
  kubectl get configmap/proofix-case12-state -n "${namespace}" -o "jsonpath={.data.$1}"
}

set_state() {
  local key="$1" value="$2" patch
  patch="$(python3 -c 'import json,sys; print(json.dumps({"data": {sys.argv[1]: sys.argv[2]}}))' "${key}" "${value}")"
  guard_run kubectl patch configmap/proofix-case12-state -n "${namespace}" --type merge -p "${patch}" >/dev/null
}

produce_markers() {
  local prefix="$1" count="$2"
  python3 -c 'import sys; p=sys.argv[1]; n=int(sys.argv[2]); [print(f"{p}-{i:04d} {p}-{i:04d}") for i in range(n)]' \
    "${prefix}" "${count}" | guard_run kubectl exec -i -n "${namespace}" kafka-0 -- \
      rpk topic produce "${topic}" --acks=-1 --format '%k %v\n' -X "brokers=${brokers}"
}

wait_for_cluster() {
  guard_run kubectl rollout status statefulset/kafka -n "${namespace}" --timeout=480s
  local deadline=$((SECONDS + 240))
  until rpk_exec cluster health --exit-when-healthy >/dev/null 2>&1; do
    (( SECONDS < deadline )) || { echo "cluster did not become healthy" >&2; return 1; }
    sleep 5
  done
}
