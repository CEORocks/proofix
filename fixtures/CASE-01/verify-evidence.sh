#!/usr/bin/env bash
set -euo pipefail

namespace="proofix-case-01"
probe_pod="$(kubectl get pod -n "${namespace}" -l app=evidence-probe \
  -o jsonpath='{.items[0].metadata.name}')"
checkout_pod_ip="$(kubectl get pod -n "${namespace}" -l app=checkout \
  -o jsonpath='{.items[0].status.podIP}')"

kubectl get virtualservice checkout -n "${namespace}" -o json
kubectl get destinationrule checkout -n "${namespace}" -o json
kubectl get pods -n "${namespace}" -l app=checkout --show-labels
kubectl exec -n "${namespace}" "${probe_pod}" -- wget -qO- \
  "http://${checkout_pod_ip}:8080/healthz"
curl -sS -o /dev/null -w 'ingress_status=%{http_code}\n' --max-time 2 \
  http://127.0.0.1:30081/
