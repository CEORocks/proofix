#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

apply_coredns_target proofix-dns-bad
python3 "${fixture_dir}/load.py" dns --base-url "${base_url}" --expect fault
verify_general_dns
echo "CASE-02 fault active: isolated zone is delayed and returns NXDOMAIN"

