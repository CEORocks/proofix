# CASE-11 — real Kafka consumer-group lag

This fixture uses a digest-pinned Redpanda 25.3 broker (Kafka-compatible) on a
single-node k3s cluster. It does not mock consumer offsets, assignments, broker
health, or lag. A six-partition `orders` topic receives a fixed 42 records per
second through Redpanda's HTTP Proxy. Three independently named consumers in
the `proofix-orders-v1` group each process and commit approximately 25 records
per second. The fault scales that Deployment from three replicas to one, making
the processing capacity lower than ingress while leaving the producer and
broker unchanged.

The consumers use the native Kafka group protocol through a hash-pinned
`kafka-python` wheel installed by an init container; they do not use the REST
proxy's consumer-instance abstraction. `lag_probe.py` captures the real
`rpk group describe` member, assignment,
partition-offset, and lag table four times. Fault verification requires exactly
one member, strictly increasing lag, at least 100 records of growth, six healthy
partitions, and zero under-replicated partitions. Recovery restores three
replicas and requires three consecutive observations with three members and
total lag no greater than 84 records. It never seeks, rewrites, or skips group
offsets and never stops or reduces the producer.

## Resource requirements

- Exactly one reachable k3s node, with `kubectl` and Python 3 on the runner.
- At least 2 allocatable CPU, 3 GiB allocatable memory, and 5 GiB free disk.
- The standard k3s `local-path` StorageClass and free NodePort `30081`.
- Outbound access to `mirror.gcr.io` on first install. Both Redpanda 25.3.8 and
  Python 3.12.5 Alpine are pinned by immutable multi-architecture digests.

The scripts exit with `UNSUPPORTED` and a nonzero status when these conditions
are not met. They never report a simulated or skipped check as successful.

## Run

On the k3s node:

```bash
cd /path/to/micro1/fixtures/CASE-11
./smoke.sh | tee case-11-smoke.log
```

From another machine, set the reachable NodePort URL:

```bash
export PROOFIX_BASE_URL=http://K3S_NODE_IP:30081
./smoke.sh | tee case-11-smoke.log
```

The individual, idempotent phases are `install.sh`, `inject.sh`,
`verify.sh fault`, `reset.sh`, and `verify.sh recovered`.
`rollback-recovery.sh` intentionally returns the Deployment to one replica for
trajectory rollback testing.

Recovered verification also sends 250 real HTTP requests in each of three
consecutive windows to the consumer health service. Every response must be 200,
HTTP 5xx rate must be `<0.001`, and p95 latency must be `<200ms`. This SLO gate
is conjunctive with the real Kafka lag/member checks; an HTTP-only success
cannot mark the case recovered.
