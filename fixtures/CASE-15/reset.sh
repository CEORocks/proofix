#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
python3 "${fixture_dir}/load.py" --base-url "${base_url}" >/dev/null
echo "CASE-15 reset is intentionally a no-op: the control is already healthy"
