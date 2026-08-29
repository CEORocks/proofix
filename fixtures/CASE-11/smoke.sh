#!/usr/bin/env bash
set -euo pipefail

fixture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"${fixture_dir}/install.sh"
"${fixture_dir}/inject.sh"
"${fixture_dir}/verify.sh" fault
"${fixture_dir}/reset.sh"
"${fixture_dir}/verify.sh" recovered
echo "CASE-11 live Kafka consumer-lag smoke passed end to end"
