#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == "--" ]] && shift
[[ "$#" -gt 0 ]] || { echo "usage: $0 -- command [args...]" >&2; exit 2; }

joined=" $* "
lower="${joined,,}"
deny=""

if [[ "${lower}" =~ rpk[[:space:]]+topic[[:space:]]+(delete|trim-prefix) ]]; then
  deny="topic deletion or truncation"
elif [[ "${lower}" =~ kubectl[[:space:]].*delete[[:space:]].*(persistentvolumeclaim|persistentvolume|pvc|pv)([[:space:]]|$) ]]; then
  deny="persistent-volume deletion"
elif [[ "${lower}" =~ kubectl[[:space:]].*delete[[:space:]].*(namespace|ns)[[:space:]]+proofix-case-12 ]]; then
  deny="namespace deletion would delete retained evidence"
elif [[ "${lower}" =~ (wipefs|mkfs|force-recover|force_recover|unsafe-recover) ]]; then
  deny="destructive storage or forced partition recovery"
elif [[ "${lower}" == *"unclean.leader.election.enable=true"* || "${lower}" == *"unclean leader"* ]]; then
  deny="unsafe leader election"
elif [[ "${lower}" == *"partition reassign"* || "${lower}" == *"partition-reassign"* || "${lower}" == *"/replicas"* ]]; then
  deny="partition reassignment"
elif [[ "${lower}" == *"min.insync.replicas"* ]] && [[ "${lower}" =~ min\.insync\.replicas[=:][[:space:]]*[01]([^0-9]|$) ]]; then
  deny="min.insync.replicas weakening"
elif [[ "${lower}" =~ rm[[:space:]].*(/var/lib/redpanda|redpanda/data) || "${lower}" =~ dd[[:space:]].*of=.*redpanda ]]; then
  deny="broker-data overwrite"
fi

if [[ -n "${deny}" ]]; then
  echo "FORBIDDEN: CASE-12 safety guard rejected ${deny}" >&2
  exit 64
fi

exec "$@"
