#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "WARNING: restoring the injected CASE-06 quota saturation" >&2
"${fixture_dir}/inject.sh"
