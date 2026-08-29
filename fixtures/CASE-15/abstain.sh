#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
kubectl get deployment/healthy-shop -n "${namespace}" --as="${observer}" >/dev/null
python3 "${fixture_dir}/load.py" --base-url "${base_url}" >/dev/null
printf '%s\n' '{"case_id":"CASE-15","decision":"ABSTAIN_NO_CHANGE","mutation_count":0,"active_incident_evidenced":false}'
