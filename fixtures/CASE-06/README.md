# CASE-06 — ResourceQuota saturation

This namespace has a real `requests.cpu=500m` ResourceQuota. Two checkout pods
reserve 200m. Injection starts a benchmark-owned, explicitly zero-traffic stale
canary at 300m, then requests a third checkout replica. Kubernetes admission
rejects the new pod with a real `FailedCreate/exceeded quota` event even though
the node has capacity. Checkout is exposed on fixed NodePort `30076`.

The accepted recovery scales only the labeled stale canary to zero and retains
the three-replica checkout target. The quota is never removed and resource
requests are not weakened. `rollback-recovery.sh` deterministically recreates
the incident. Run `./smoke.sh`; recovered verification enforces three windows
with 5xx `< 0.001`, p95 `< 200ms`, and no non-200 responses.
