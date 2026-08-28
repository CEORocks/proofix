# CASE-07 — Java heap OOM / Exit 137

This is a real, single-node-k3s fixture for the authoritative CASE-07 contract.
It exposes `pricing-api` as a NodePort service on port `30077` and uses a
digest-pinned Eclipse Temurin 17 JDK image. There are no mocked Kubernetes
states or synthetic exit codes.

The Java service retains touched 8 MiB chunks up to 70% of the JVM maximum
heap. The healthy and recovered profile uses `-Xmx128m` inside a `256Mi`
container limit, so retention stabilizes with non-heap headroom. Injection
changes only the JVM maximum to `-Xmx512m`. The unchanged `/price` load then
drives resident memory through the cgroup limit, and k3s records the kernel
termination as `OOMKilled` with exit code `137`.

## Preconditions

- A single-node k3s cluster with at least 1 GiB allocatable memory.
- `kubectl` configured for that cluster and Python 3 available on the node.
- TCP port `30077` available for the fixed NodePort.
- No active node `MemoryPressure` condition. `verify.sh` captures full node
  evidence so this can be checked rather than inferred.

Run the smoke test **on the k3s node**:

```bash
cd /path/to/micro1/fixtures/CASE-07
./smoke.sh | tee case-07-smoke.log
```

When running from another machine, point the scripts at the node's reachable
address:

```bash
export PROOFIX_BASE_URL=http://K3S_NODE_IP:30077
./smoke.sh | tee case-07-smoke.log
```

The explicit sequence is:

```bash
./install.sh              # healthy deployment + three strict SLO windows
./inject.sh               # -Xmx512m under 256Mi; drives real cgroup OOM
./verify.sh fault         # captures and asserts OOMKilled / exit 137 evidence
./reset.sh                # accepted recovery: restore -Xmx128m
./verify.sh recovered     # 3 x 250 requests, restart guard, strict SLO checks
```

The post-recovery check preserves the handover SLO exactly: each of three
consecutive windows must have HTTP 5xx rate `< 0.001` and p95 latency `< 200ms`.
It additionally fails on any non-200 response or container restart.

## Recovery and rollback

`recovery-patch.yaml` is the accepted low-risk recovery: reduce maximum heap to
the known-safe 128 MiB while keeping the 256 MiB limit and non-heap headroom.
It does not disable limits, change node/kernel OOM behavior, alter the service,
or change the load. `rollback-recovery-patch.yaml` restores the exact injected
JVM flags for reversible-trajectory validation. Running
`rollback-recovery.sh` therefore deliberately reintroduces the incident and is
not an operational recovery step.

The scripts emit the Deployment, Pod status, restart count, last termination
reason/exit code, JVM arguments, resource limit, and node conditions needed to
distinguish a container cgroup OOM from node pressure or a generic exit 137.

