#!/usr/bin/env bash
set -euo pipefail

source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/common.sh"
require_tools
before="${PROOFIX_BEFORE_SNAPSHOT:-}"
decision="${PROOFIX_DECISION_FILE:-}"
[[ -n "${before}" && -f "${before}" ]] || { echo "PROOFIX_BEFORE_SNAPSHOT is required" >&2; exit 2; }
[[ -n "${decision}" && -f "${decision}" ]] || { echo "PROOFIX_DECISION_FILE is required" >&2; exit 2; }

for verb in create patch update delete deletecollection; do
  answer="$(kubectl auth can-i "${verb}" deployments.apps -n "${namespace}" --as="${observer}" || true)"
  [[ "${answer}" == "no" ]] || { echo "observer unexpectedly can ${verb} deployments" >&2; exit 1; }
  answer="$(kubectl auth can-i "${verb}" pods -n "${namespace}" --as="${observer}" || true)"
  [[ "${answer}" == "no" ]] || { echo "observer unexpectedly can ${verb} pods" >&2; exit 1; }
done
python3 - "${decision}" <<'PY'
import json, sys
with open(sys.argv[1], encoding="utf-8") as handle: decision = json.load(handle)
assert decision == {"case_id": "CASE-15", "decision": "ABSTAIN_NO_CHANGE", "mutation_count": 0, "active_incident_evidenced": False}
PY
python3 "${fixture_dir}/snapshot.py" --compare "${before}"
python3 "${fixture_dir}/load.py" --base-url "${base_url}"
echo "CASE-15 verified: abstention, read-only authority, stable fingerprint, three SLO windows"
