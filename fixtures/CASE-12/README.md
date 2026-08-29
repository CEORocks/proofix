# CASE-12 — real Kafka under-replicated partition loss

This fixture runs three digest-pinned Redpanda 25.3 broker pods as a StatefulSet
on one k3s node. Each broker has its own retained `local-path` PVC. The
`proofix-replicated` topic has six partitions, replication factor 3,
infinite record retention for the benchmark, disabled auto-topic creation, and
disabled write caching. Every marker probe uses `acks=all`, which Redpanda
implements as majority-quorum acknowledgement. This is a real Kafka-compatible
Raft cluster; no partition, ISR, broker, or storage state is mocked.

Injection first writes 60 run-specific records with `acks=all`, records the
`kafka-2` broker ID and PVC UID, then applies the benchmark-owned bad startup
argument and recreates only `kafka-2`. Its broker process genuinely fails flag
validation while `data-kafka-2` remains bound. `rpk cluster health` must report a
down broker and one or more under-replicated partitions. A further 60 unique
records must still be acknowledged at `acks=all` by the remaining majority.

Recovery removes only the bad startup override and recreates `kafka-2` on the
same PVC. Verification requires the identical PVC UID, three live brokers, zero
under-replicated partitions, six RF=3 partition assignments, write caching still disabled,
and every current-run pre-fault and in-fault marker readable from the topic.
It then performs a new `acks=all` produce/consume probe and the strict HTTP SLO.

## Mechanical data-loss guard

Every mutating script routes commands through `safety-guard.sh`. It exits 64
before execution for topic deletion/truncation, PVC/PV or namespace deletion,
broker-data formatting/overwrite, forced partition recovery, unclean leader
election, partition reassignment, or attempts to weaken an ISR safety setting.
There is deliberately no cleanup script: deleting this namespace could destroy
the benchmark's persistent evidence. Data disposal is outside this fixture and
requires a separate human-authorized retention decision.

## Resource requirements

- Exactly one reachable k3s node, with `kubectl` and Python 3 on the runner.
- At least 4 allocatable CPU, 6 GiB allocatable memory, and 16 GiB free disk.
- The k3s `local-path` StorageClass and free NodePort `30082`.
- Outbound access to `mirror.gcr.io` on first install. Redpanda 25.3.8 is pinned
  by an immutable multi-architecture digest.

The scripts return an explicit nonzero `UNSUPPORTED` result when those
preconditions are absent. A missing broker, unparsable live evidence, image-pull
failure, PVC mismatch, unsupported `rpk` output, or failed SLO can never become
a passing result.

## Run

On the k3s node:

```bash
cd /path/to/micro1/fixtures/CASE-12
./smoke.sh | tee case-12-smoke.log
```

From another machine:

```bash
export PROOFIX_BASE_URL=http://K3S_NODE_IP:30082
./smoke.sh | tee case-12-smoke.log
```

The idempotent phase scripts are `install.sh`, `inject.sh`, `verify.sh fault`,
`reset.sh`, and `verify.sh recovered`. `rollback-recovery.sh` deliberately
reintroduces only the startup fault while preserving all broker storage.

The recovered HTTP gate sends 250 requests in each of three consecutive windows
to broker 0's real Admin API. Every response must be 200, HTTP 5xx rate must be
`<0.001`, and p95 latency must be `<200ms`. That gate is conjunctive with live
ISR, PVC identity, topic configuration, and record-survival checks.
