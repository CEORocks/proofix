#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-11"
broker_pod="redpanda-0"
brokers="redpanda-0.redpanda.proofix-case-11.svc.cluster.local:9092"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30081}"

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
    echo "UNSUPPORTED: CASE-11 is preregistered for k3s; server is ${version}" >&2
    exit 3
  }
  nodes="$(kubectl get nodes --no-headers | wc -l | tr -d ' ')"
  [[ "${nodes}" == "1" ]] || {
    echo "UNSUPPORTED: CASE-11 requires exactly one k3s node; found ${nodes}" >&2
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
if cpu < 2 or memory < 3*1024**3:
    raise SystemExit("UNSUPPORTED: CASE-11 requires >=2 allocatable CPU and >=3 GiB memory")
'
}

rpk_exec() {
  kubectl exec -n "${namespace}" "${broker_pod}" -- rpk "$@" -X "brokers=${brokers}"
}

wait_for_workloads() {
  kubectl rollout status statefulset/redpanda -n "${namespace}" --timeout=300s
  kubectl rollout status deployment/orders-producer -n "${namespace}" --timeout=180s
  kubectl rollout status deployment/orders-consumer -n "${namespace}" --timeout=180s
}
