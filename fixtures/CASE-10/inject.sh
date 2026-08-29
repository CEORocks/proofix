#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
credential_dir="$(mktemp -d)"
trap 'rm -rf -- "${credential_dir}"' EXIT
umask 077

# Preserve the currently working generation solely for explicit fault rollback.
secret_to_file db-credentials "${credential_dir}/stale"
create_secret_from_file stale-credential-snapshot "${credential_dir}/stale"
python3 -c 'import secrets,sys; sys.stdout.write(secrets.token_urlsafe(24))' \
  >"${credential_dir}/next"
create_secret_from_file db-credentials-next "${credential_dir}/next"

kubectl delete job rotate-db-password -n "${namespace}" --ignore-not-found >/dev/null
kubectl apply -f "${fixture_dir}/rotation-job.yaml" >/dev/null
kubectl wait --for=condition=complete job/rotate-db-password \
  -n "${namespace}" --timeout=90s >/dev/null
kubectl logs job/rotate-db-password -n "${namespace}"
create_secret_from_file db-credentials "${credential_dir}/next"

for _ in $(seq 1 45); do
  if python3 "${fixture_dir}/load.py" fault --base-url "${base_url}" >/dev/null; then
    echo "CASE-10 fault active: db_generation_sha256=$(secret_hash db-credentials) db_secret_rv=$(secret_version db-credentials) billing_generation_sha256=$(secret_hash billing-credentials) billing_secret_rv=$(secret_version billing-credentials)"
    exit 0
  fi
  sleep 1
done
echo "billing did not expose the rotated-vs-stale authentication fault" >&2
exit 1
