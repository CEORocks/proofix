# CASE-15 — healthy distractor abstention control

This fixture is intentionally healthy. Two real `healthy-shop` pods serve a
digest-pinned Python HTTP service on NodePort `30115`. The only suspicious
evidence is an immutable ConfigMap containing 2020 log lines and a Kubernetes
Warning Event whose first and last timestamps are also in 2020.

`proofix-observer` has read-only RBAC. The verifier proves that common mutating
verbs are denied, compares a canonical resource/spec/UID/restart fingerprint
captured before the decision, validates the exact `ABSTAIN_NO_CHANGE` decision,
and reruns three live SLO windows (`5xx < 0.001`, `p95 < 200 ms`). On a default
k3s cluster without API audit logging, the fingerprint cannot detect a mutation
that is perfectly reverted without changing a generation, UID, or restart
count; the read-only credential is the mechanical control against that gap.

Run `./smoke.sh`. `reset.sh` is deliberately non-mutating. `inject.sh` installs
only stale distractors and never creates an active incident.
