#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

kubectl apply -f "${fixture_dir}/namespace.yaml"
kubectl apply -f "${fixture_dir}/dns-upstreams.yaml"
kubectl apply -f "${fixture_dir}/app.yaml"
wait_fixture
save_original_corefile
apply_coredns_target proofix-dns-good
verify_general_dns
python3 "${fixture_dir}/load.py" slo --base-url "${base_url}" --requests 250
echo "CASE-02 installed healthy at ${base_url}"

