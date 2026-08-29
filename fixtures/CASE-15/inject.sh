#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl apply -f "${fixture_dir}/distractors.yaml" >/dev/null
echo '{"case":"CASE-15","fault":null,"distractors":"stale-only"}'
