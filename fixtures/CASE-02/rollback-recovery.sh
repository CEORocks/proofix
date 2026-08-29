#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

apply_coredns_target proofix-dns-bad
echo "CASE-02 recovery rolled back; the benchmark fault is active again"

