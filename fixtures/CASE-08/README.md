# CASE-08: CPU throttling and liveness restart cascade

This fixture runs a real Java search service in `proofix-case-08`. Injection caps it
at `100m` while a fixed 32-concurrency load competes with an intentionally costly
one-second liveness probe. Evidence is accepted only when cgroup v2 `nr_throttled`
increases, kubelet records `Liveness probe failed`, and the container restarts at
least twice. The recovery restores a bounded three-CPU limit; it never removes the
probe or weakens traffic or SLOs.

The immutable Temurin image is digest-pinned. The service is exposed on NodePort
`30078`. On the k3s node:

```bash
cd fixtures/CASE-08
./smoke.sh | tee case-08-smoke.log
```

From another host, set `PROOFIX_BASE_URL=http://K3S_NODE_IP:30078` for every
script. Individual lifecycle commands are `install.sh`, `inject.sh`,
`verify.sh fault`, `reset.sh`, `verify.sh recovered`, and
`rollback-recovery.sh`.

Recovered verification requires exactly three consecutive windows, HTTP 5xx
rate `< 0.001`, p95 latency `< 200ms`, zero non-200 responses, and no restart
during measurement. `install.sh` and `reset.sh` are safe to repeat. Rollback is
explicit because it deliberately restores the fault.
