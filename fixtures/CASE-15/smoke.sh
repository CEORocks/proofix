#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
snapshot_file="$(mktemp)"; decision_file="$(mktemp)"
trap 'rm -f "${snapshot_file}" "${decision_file}"' EXIT
"${fixture_dir}/install.sh"
"${fixture_dir}/inject.sh"
python3 "${fixture_dir}/snapshot.py" --output "${snapshot_file}"
"${fixture_dir}/abstain.sh" >"${decision_file}"
PROOFIX_BEFORE_SNAPSHOT="${snapshot_file}" PROOFIX_DECISION_FILE="${decision_file}" "${fixture_dir}/verify.sh"
