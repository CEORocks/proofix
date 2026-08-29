#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
credential_dir="$(mktemp -d)"
trap 'rm -rf -- "${credential_dir}"' EXIT
secret_to_file db-credentials "${credential_dir}/current"
create_secret_from_file billing-credentials "${credential_dir}/current"
roll_billing_for_secret_version
wait_for_workloads
echo "CASE-10 recovery synchronized generation_sha256=$(secret_hash billing-credentials) billing_secret_rv=$(secret_version billing-credentials)"
