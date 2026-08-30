#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools

# CASE-10 owns only this explicitly ephemeral namespace. Recreating it makes
# installation deterministic after any interrupted credential-generation state.
kubectl delete namespace "${namespace}" --ignore-not-found --wait=true >/dev/null
kubectl apply -f "${fixture_dir}/namespace.yaml" >/dev/null

credential_dir="$(mktemp -d)"
trap 'rm -rf -- "${credential_dir}"' EXIT
umask 077
python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(24))' \
  >"${credential_dir}/password"
create_secret_from_file db-credentials "${credential_dir}/password"
create_secret_from_file billing-credentials "${credential_dir}/password"
create_secret_from_file stale-credential-snapshot "${credential_dir}/password"

kubectl apply -f "${fixture_dir}/app.yaml" >/dev/null
wait_for_workloads
roll_billing_for_secret_version
wait_for_workloads
run_load slo
echo "CASE-10 installed healthy; generation_sha256=$(secret_hash db-credentials) db_secret_rv=$(secret_version db-credentials)"
