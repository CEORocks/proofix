# CASE-14 — StorageClass provisioning failure

The fixture creates a real StorageClass whose provisioner is
`proofix.invalid/no-such-provisioner`. The benchmark-owned `uploads` PVC stays
Pending and the pod stays unschedulable. Recovery first proves the claim is
Pending, unbound, evaluator-labelled empty, and not mounted by a Running pod;
only then does it recreate that exact claim against `local-path` (or
`PROOFIX_GOOD_STORAGE_CLASS`). It seeds and reads a real file and runs three
strict HTTP SLO windows on NodePort `30114`.

Run `./smoke.sh` on k3s. Re-running recovery is idempotent. Reintroducing the
fault after the recovered volume is bound and seeded is deliberately refused:
`rollback-recovery.sh` exits 3 rather than delete data. A clean evaluator-owned
namespace is required for a fresh fault trial.
