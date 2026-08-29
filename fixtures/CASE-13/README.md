# CASE-13 — real PVC Multi-Attach, with explicit capability gate

The fixture provisions evaluator-seeded data on a real ReadWriteOnce PVC. On a
cluster with at least two Ready nodes and an attach-required CSI driver,
injection holds the original pod in Terminating via a benchmark finalizer and
creates its replacement on the second node. It passes only after Kubernetes
emits a real Multi-Attach/attachment-conflict Event and a matching
`VolumeAttachment` exists. Recovery removes the benchmark finalizer, waits for
the original object to disappear and for the replacement to attach, then proves
ledger continuity and three strict SLO windows on NodePort `30113`.

Default single-node k3s uses `rancher.io/local-path`, which has no attach-required
CSI driver or VolumeAttachment state. `inject.sh` therefore prints
`UNSUPPORTED_INFRASTRUCTURE` and exits 3 **before mutating the healthy pod**. It
never turns a scheduler/node-affinity symptom into a fake Multi-Attach pass.

Use `PROOFIX_CASE13_STORAGE_CLASS` on a supported multi-node CSI cluster. Safe
rollback requires the original node name in `PROOFIX_CASE13_PRIMARY_NODE` and
always deletes/waits for the replacement before reattachment.
