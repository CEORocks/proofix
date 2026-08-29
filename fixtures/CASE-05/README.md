# CASE-05 — required PodAntiAffinity replica deadlock

On the required single-node k3s cluster, this fixture keeps the desired replica
count at two. Injection switches hostname anti-affinity from preferred to
required. One real pod schedules and the second remains Pending because the
only topology domain already contains a matching pod; scheduler events are
captured and asserted. Fixed NodePort: `30075`.

The accepted recovery changes only the rule back to preferred, retaining two
ready replicas and the intended spreading preference. It does not reduce the
replica count or alter scheduler policy. `rollback-recovery.sh` restores the
fault. Run `./smoke.sh`; recovered verification requires three consecutive
windows with 5xx `< 0.001`, p95 `< 200ms`, and no failed requests.
