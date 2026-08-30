# ProofFix engineering changelog and failure-derived insights

This changelog records the iterations that materially changed the submitted system. It includes failed approaches because the benchmark's main lesson is that agent reliability depends as much on harness and verification engineering as on model reasoning.

## Iteration 1 — Problem and metric freeze

- Selected the last-mile Kubernetes recovery bottleneck: turning plausible diagnosis into a safe, verified state transition for on-call SREs.
- Defined the nine-stage workflow, bounded tool surface, executable rollback requirement, evidence closure, and conjunctive Verified Recovery Success (VRS).
- Froze 15 cases, three trials, a ReAct baseline, identical Flash model backend, action budgets, load windows, and deterministic paired statistics.

**Insight:** Root-cause quality cannot be the primary metric. A recovery only counts when live service health, semantic fixture state, safety, trace integrity, and evidence closure all pass together.

## Iteration 2 — Real fixtures replaced simulated success

- Reworked cases to use live Kubernetes state, continuous HTTP load, semantic verification scripts, and pinned images.
- Added special evidence gates for Istio routing, CoreDNS, RBAC, Secret synchronization, Kafka safety, PVC attachment, and safe abstention.
- CASE-13 initially used GKE PD CSI to validate real `VolumeAttachment` behavior rather than accepting a fake local-path approximation.

**Failure:** Single-node local storage cannot reproduce a cross-node ReadWriteOnce attachment conflict.

**Insight:** Capability gates must reject unsupported infrastructure before scoring. A fixture that cannot physically express the fault is not a benchmark.

## Iteration 3 — Harness transport and lifecycle hardening

- Replaced fragile direct NodePort assumptions with supervised local Kubernetes port-forwarding and SSH tunnel lifecycle control.
- Increased fixture and Kubernetes command margins for cold image pulls and controller warm-up.
- Made runs resumable by valid `(case, system, trial)` key and flushed every result and trajectory to disk.
- Preserved incomplete and infrastructure-invalid attempts separately from scored output.

**Failures:** Remote HTTP probes intermittently closed connections; stale port-forward children survived interrupted runs; deployment readiness occasionally exceeded the original 30-second client timeout.

**Insight:** The evaluator transport is part of the experiment. If it is less reliable than the system under test, it measures the harness instead of the agent.

## Iteration 4 — High-volume observation and Antigravity boundary fixes

- Added deterministic context compaction above 400k characters, with original-size and SHA-256 provenance markers.
- Passed the JSON schema to Antigravity by file and pinned `gemini-3.7-flash-medium` explicitly.
- Ignored malformed truncated intermediate stream events while still requiring a valid final schema-constrained result.
- Added infrastructure-only stack traces to failed run artifacts.

**Failure:** Large Kubernetes event lists crossed a 200,000-character display boundary and produced `JSONDecodeError` records without enough call-site evidence.

**Insight:** Compaction must be symmetric across baseline and agent, and truncation handling must distinguish diagnostic echo noise from the authoritative final result.

## Iteration 5 — Provider-independent CASE-13 execution

- Deleted the temporary GKE cluster after the PD CSI fixture was validated.
- Provisioned a two-node k3s topology on Vultr with Longhorn v1.11.3 and a one-replica `longhorn-single` StorageClass.
- Opened only the K3s overlay and pod-CIDR firewall paths required between the two nodes.
- Generalized the attachment detector to accept both `Multi-Attach` and Longhorn's equivalent `FailedAttachVolume: Waiting for detach ... Volume is already used` evidence, while still requiring the matching live `VolumeAttachment`.
- Synced three valid ProofFix trials, then removed the worker, Vultr instance, temporary API SSH key, Kubernetes node record, and scoped firewall rules.

**Failures:** Longhorn's webhook initially could not cross the VXLAN overlay because UFW denied routed pod traffic. Longhorn also reports attachment contention with different event text than GKE PD CSI.

**Insight:** Benchmark semantics should be provider-independent, but evidence requirements must remain strict. Match the state transition and authoritative controller objects, not one cloud vendor's exact string.

## Iteration 6 — Final validity classification fix

- Traced three persistent CASE-05 invalids through otherwise complete trajectories.
- Confirmed the agent correctly patched hard anti-affinity, restored service, and completed all SLO windows.
- Found that the automatic rollback restored the intentionally broken anti-affinity state, after which `rollout status` timed out by design. That expected rollback error escaped the workflow and mislabeled an agent outcome as infrastructure-invalid.
- Changed rollback errors after failed SLO verification into hash-chained `rollback_failed` events and valid failed outcomes. Added regression coverage, then reran exactly the three missing CASE-05 keys.

**Insight:** Agent failure is data. Execution or rollback failure must become a scored outcome when the infrastructure and evaluator remain healthy; otherwise the harness silently inflates performance by voiding difficult runs.

## Frozen benchmark outcome

- **90 valid scored runs**, 45 paired comparisons, and **2,697 verified hash-chained events**.
- ReAct baseline VRS: **26.7% (12/45)**.
- ProofFix VRS: **37.8% (17/45)**.
- Paired lift: **+11.1 percentage points**; bootstrap 95% CI **[0.0, 22.2] pp**; exact McNemar **p=0.125**.
- Forbidden-action runs: **0 for both systems**.
- CASE-15 safe abstention: **100% for both systems**.
- Seventy infrastructure-invalid attempts are retained in `artifacts/diagnostics/infrastructure-invalid.final.jsonl` and excluded from scoring.

The preregistered 80% VRS and statistical-significance gates were not met. Routing cases showed the clearest benefit (CASE-01: 0/3 to 3/3; CASE-02: 1/3 to 3/3), while messaging, storage, and evidence closure remain the highest-value next engineering targets.

## Protocol deviation disclosed

The original protocol called for rerunning a complete pair after any infrastructure-invalid attempt. During distributed recovery, the harness resumed only missing valid keys while retaining already valid counterparts. The final matrix remains complete and uses identical case manifests, systems, model, trial IDs, and evaluator, but this selective-resume behavior is a disclosed deviation and should be removed in a future replication by scheduling atomic paired trials.
