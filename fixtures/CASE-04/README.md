# CASE-04 — nodeSelector/taints mismatch

This fixture requires exactly one k3s node. It labels that benchmark node
`storage=nvme` and applies the narrow taint `dedicated=reports:NoSchedule`.
Injection changes the pod to the incorrect `disk=nvme` selector and removes
its toleration, producing a real Pending pod and FailedScheduling evidence for
both constraints. The accepted recovery restores `storage=nvme` and the exact
`dedicated=reports` toleration; no wildcard toleration or global scheduler
change is used. HTTP is exposed on fixed NodePort `30074`.

Run `./smoke.sh`; it always invokes `cleanup.sh` to remove the namespace and
the fixture-owned node taint/labels. If running individual scripts, call
`cleanup.sh` when finished. `rollback-recovery.sh` intentionally recreates the
fault. Recovered verification enforces three windows with 5xx `< 0.001` and
p95 `< 200ms`.
