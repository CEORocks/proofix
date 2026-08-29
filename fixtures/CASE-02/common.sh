#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
namespace="proofix-case-02"
deployment="dns-dependent-api"
base_url="${PROOFIX_BASE_URL:-http://127.0.0.1:30072}"

require_tools() {
  command -v kubectl >/dev/null || {
    echo "kubectl is required" >&2
    exit 2
  }
  command -v python3 >/dev/null || {
    echo "python3 is required" >&2
    exit 2
  }
  kubectl version --request-timeout=10s >/dev/null
  kubectl get deployment/coredns configmap/coredns -n kube-system >/dev/null
}

wait_fixture() {
  kubectl rollout status deployment/proofix-dns-good -n "${namespace}" --timeout=180s
  kubectl rollout status deployment/proofix-dns-bad -n "${namespace}" --timeout=180s
  kubectl rollout status "deployment/${deployment}" -n "${namespace}" --timeout=180s
}

save_original_corefile() {
  if kubectl get configmap/proofix-case-02-coredns-original \
      -n "${namespace}" >/dev/null 2>&1; then
    return
  fi
  local original
  original="$(mktemp)"
  kubectl get configmap/coredns -n kube-system \
    -o go-template='{{index .data "Corefile"}}' >"${original}"
  kubectl create configmap proofix-case-02-coredns-original -n "${namespace}" \
    --from-file=Corefile="${original}"
  rm -f -- "${original}"
}

upstream_ip() {
  local service="$1"
  kubectl get service "${service}" -n "${namespace}" \
    -o jsonpath='{.spec.clusterIP}'
}

apply_coredns_target() {
  local service="$1"
  local target_ip current_file rendered_file patch_file
  target_ip="$(upstream_ip "${service}")"
  [[ "${target_ip}" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || {
    echo "invalid ClusterIP for ${service}: ${target_ip}" >&2
    exit 1
  }
  current_file="$(mktemp)"
  rendered_file="$(mktemp)"
  patch_file="$(mktemp)"

  kubectl get configmap/coredns -n kube-system \
    -o go-template='{{index .data "Corefile"}}' >"${current_file}"
  python3 "${fixture_dir}/corefile.py" --target "${target_ip}:5353" \
    <"${current_file}" >"${rendered_file}"
  python3 - "${rendered_file}" >"${patch_file}" <<'PY'
import json
import pathlib
import sys

print(json.dumps({"data": {"Corefile": pathlib.Path(sys.argv[1]).read_text()}}))
PY
  kubectl patch configmap/coredns -n kube-system --type merge \
    --patch-file "${patch_file}"
  rm -f -- "${current_file}" "${rendered_file}" "${patch_file}"
  kubectl rollout restart deployment/coredns -n kube-system
  kubectl rollout status deployment/coredns -n kube-system --timeout=180s
  wait_for_dns_target "${service}"
}

wait_for_dns_target() {
  local service="$1"
  local expected_ip attempt evidence
  expected_ip="$(upstream_ip "${service}")"
  for attempt in $(seq 1 60); do
    evidence="$(kubectl exec -n "${namespace}" "deployment/${deployment}" -- \
      python -c 'import json,urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/diagnostics", timeout=2).read().decode())' \
      2>/dev/null || true)"
    if [[ "${service}" == "proofix-dns-good" && "${evidence}" == *'"ok": true'* ]]; then
      echo "CoreDNS isolated zone now forwards to ${service} (${expected_ip})"
      return
    fi
    if [[ "${service}" == "proofix-dns-bad" && "${evidence}" == *'"rcode": 3'* ]]; then
      echo "CoreDNS isolated zone now forwards to ${service} (${expected_ip})"
      return
    fi
    sleep 1
  done
  echo "CoreDNS did not converge on ${service} (${expected_ip})" >&2
  return 1
}

verify_general_dns() {
  kubectl exec -i -n "${namespace}" "deployment/${deployment}" -- python - <<'PY'
import json
import socket
import time

started = time.perf_counter()
addresses = sorted({item[4][0] for item in socket.getaddrinfo(
    "kubernetes.default.svc.cluster.local", 443, socket.AF_INET
)})
latency_ms = (time.perf_counter() - started) * 1000
evidence = {"query": "kubernetes.default.svc.cluster.local", "addresses": addresses,
            "latency_ms": round(latency_ms, 3), "healthy": bool(addresses)}
print(json.dumps(evidence, sort_keys=True))
if not addresses:
    raise SystemExit(1)
PY
}
