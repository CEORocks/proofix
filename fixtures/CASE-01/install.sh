#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
kubectl apply -f "${fixture_dir}/base.yaml"
kubectl wait --for=condition=Available deployment/checkout-gateway \
  -n proofix-case-01 --timeout=300s
kubectl wait --for=condition=Available deployment/evidence-probe \
  -n proofix-case-01 --timeout=180s
kubectl rollout status deployment/istio-ingressgateway -n istio-system --timeout=180s
