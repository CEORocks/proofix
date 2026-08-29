#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
echo "WARNING: restoring the stale CASE-10 application credential" >&2
credential_dir="$(mktemp -d)"
trap 'rm -rf -- "${credential_dir}"' EXIT
secret_to_file stale-credential-snapshot "${credential_dir}/stale"
create_secret_from_file billing-credentials "${credential_dir}/stale"
roll_billing_for_secret_version
wait_for_workloads
echo "CASE-10 recovery rollback complete; stale_generation_sha256=$(secret_hash billing-credentials)"
