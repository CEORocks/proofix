#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
kubectl apply -f "${fixture_dir}/observer-rbac.yaml"
kubectl apply -f "${fixture_dir}/distractors.yaml"
kubectl rollout status deployment/healthy-shop -n "${namespace}" --timeout=180s
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-15 installed healthy with immutable stale distractors"
