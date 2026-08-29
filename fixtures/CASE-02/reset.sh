#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

apply_coredns_target proofix-dns-good
echo "CASE-02 accepted recovery applied: one isolated CoreDNS upstream corrected"

