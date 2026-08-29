# CASE-02 — CoreDNS latency and NXDOMAIN

This fixture runs a real DNS-dependent HTTP workload on dedicated single-node
k3s. The fixed NodePort is `30072`. Every `/healthz` and `/checkout` request
sends a DNS query to the nameserver in the pod's `/etc/resolv.conf`; in k3s,
that is the cluster CoreDNS Service. A successful HTTP response therefore
depends on the real pod-to-CoreDNS-to-upstream path.

The fixture owns only the isolated `bench.proofix` zone. It appends a clearly
marked, idempotently replaced server block to the existing CoreDNS `Corefile`.
It does not replace or weaken the normal `.:53` server block. Both fixture
upstreams and the HTTP workload use a digest-pinned Python 3.12 Alpine image.

## Fault and accepted recovery

Injection changes one value in the isolated CoreDNS block: its `forward`
target. The fault target waits 350 ms and returns DNS RCODE 3 (NXDOMAIN) for
`backend.bench.proofix`. The HTTP workload consequently returns 503 after the
same DNS delay. General cluster DNS is checked independently by resolving
`kubernetes.default.svc.cluster.local` from the workload pod.

The accepted recovery is the minimal reversible configuration correction:
point that isolated `forward` block at the healthy upstream. It immediately
returns `198.51.100.42` with RCODE 0. `rollback-recovery.sh` restores the exact
fault target. The original pre-fixture Corefile is preserved once in the
`proofix-case-02-coredns-original` ConfigMap for audit evidence.

## Preconditions

- A dedicated single-node k3s cluster; this fixture restarts its CoreDNS
  Deployment after each isolated-zone configuration change.
- `kubectl` configured for that cluster and Python 3 on the machine running the
  scripts.
- Fixed NodePort `30072` available.
- Network access to pull the pinned image on first install.

Run the complete live smoke on the k3s node:

```bash
cd /path/to/micro1/fixtures/CASE-02
./smoke.sh | tee case-02-smoke.log
```

From another machine, use the node's reachable address:

```bash
cd /path/to/micro1/fixtures/CASE-02
export PROOFIX_BASE_URL=http://K3S_NODE_IP:30072
./smoke.sh | tee case-02-smoke.log
```

Or run each idempotent phase explicitly:

```bash
./install.sh              # deploy fixture, healthy CoreDNS target, 3 SLO windows
./inject.sh               # switch isolated zone to delayed NXDOMAIN upstream
./verify.sh fault         # assert latency, RCODE 3, HTTP 503, general DNS healthy
./reset.sh                # accepted one-target CoreDNS correction
./verify.sh recovered     # assert DNS answer and strict 3-window HTTP SLO
./rollback-recovery.sh    # deliberately restore the fault for rollback testing
```

No script fabricates a result. The smoke exits nonzero unless live evidence
shows the isolated query has at least 300 ms latency plus NXDOMAIN during the
fault, general cluster DNS remains healthy, recovery returns the expected A
record, and all three consecutive 250-request windows have zero non-200s,
HTTP 5xx rate `< 0.001`, and p95 latency `< 200ms`.

