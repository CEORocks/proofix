# ProofFix Video Pitch & Live Side-by-Side Demonstration Script

> **A timed 5-minute (300-second) narration and shot-by-shot storyboard comparing ProofFix against a standard ReAct baseline during live Kubernetes incident recovery.**

---

## Executive Overview

- **Total Duration:** 5:00 (300 Seconds)
- **Target Audience:** Hackathon Judges, Lead SREs, Platform Architects, Systems Researchers.
- **Core Narrative:** Root-cause diagnosis is a vanity metric when an on-call responder needs a safe recovery. Generic ReAct agents jump to unsupported conclusions, attempt uncoordinated mutations, and declare victory without verifying whole-system SLOs. ProofFix enforces a closed-loop nine-stage state machine that generates competing hypotheses, executes discriminating tests, gates mutations behind a deterministic safety policy, and proves multi-window recovery under live traffic.
- **Featured Live Scenarios:**
  - **Primary Side-by-Side Demo:** `CASE-01` (Istio VirtualService routing to an undefined subset under continuous live traffic).
  - **Secondary Security Highlight:** `CASE-10` (DB Password Secret rotation without credential exposure).
  - **Control Verification:** `CASE-15` (Healthy system distractor; proving zero-mutation safe abstention).

---

## Timeline & Scene Progression

| Scene | Timecode | Duration | Title | Core Focus |
|---|:---:|:---:|---|---|
| **Scene 1** | `0:00 - 0:45` | 45s | **The Trap: The Last Mile of Incident Response** | The operational crisis of cloud outages; why LLM chat RCA fails responders. |
| **Scene 2** | `0:45 - 1:30` | 45s | **The Baseline Gap: Recovery Without Proof** | ReAct restores traffic but fails strict VRS because its final claims are not evidence-closed. |
| **Scene 3** | `1:30 - 2:45` | 75s | **Inside ProofFix: The 9-Stage Evidence Machine** | Deep dive into the closed-loop architecture, challenger tests, and safety gate. |
| **Scene 4** | `2:45 - 4:00` | 75s | **Live Showdown & The Incident Recovery Packet** | ProofFix resolves `CASE-01`, passes 3 SLO windows, and closes every critical claim. |
| **Scene 5** | `4:00 - 4:35` | 35s | **The 15-Case Benchmark & Reproducibility** | 90-run paired matrix, 6 failure families, abstention control, hash-chained ledger. |
| **Scene 6** | `4:35 - 5:00` | 25s | **The Hot Take & Closing Call to Action** | *"Don't trust the diagnosis. Trust the proof of recovery."* |

---

## Shot-by-Shot Storyboard & Timed Narration

---

### Scene 1: The Trap — The Last Mile of Incident Response
**Timecode:** `0:00 - 0:45` (Duration: 45 seconds)

```
+-------------------------------------------------------------------------------+
| VISUAL LAYOUT (Full Screen)                                                   |
| - High-contrast PagerDuty/Alertmanager incident firing:                        |
|   "CRITICAL: checkout ingress HTTP 503 Spike — Istio route has no backend"   |
| - Split infographic showing recent empirical research findings:               |
|   * ITBench: 13.8% SRE resolution rate                                        |
|   * Cloud-OpsBench: 0.76 RCA vs 0.38 Evidence Closure                         |
|   * R2Act: 99% root-service localization vs 36% valid action selection        |
+-------------------------------------------------------------------------------+
```

- **Voiceover Narration (`0:00 - 0:45`):**
  > *"It’s 3:00 AM. An availability alert fires across your Kubernetes cluster. Traffic is dropping, error rates hit 100%, and the clock is ticking on your SLO.*
  >
  > *Today’s AI coding assistants can generate a plausible-sounding root cause in seconds. But in production, a diagnosis is not a solution. Recent research proves it: on ITBench, state-of-the-art agents resolved only 13.8% of SRE incidents. On Cloud-OpsBench, models found the root cause 76% of the time, but closed the evidence chain in only 38%. And on R2Act, even with near-perfect service localization, valid recovery actions dropped to 36%.*
  >
  > *Why? Because conversational models hallucinate telemetry, jump to premature conclusions, propose destructive actions without rollbacks, and declare success without proving the system actually recovered under load.*
  >
  > *Meet **ProofFix**: the first evidence-closed, policy-gated incident recovery agent that proves recovery before declaring victory."*

- **On-Screen Callouts:**
  - `ALERT: checkout ingress routing to undefined subset v2`
  - `THE RCA GAP: Correct Diagnosis ≠ Safe Recovery`
  - `PROOFIX: Evidence-Closed Kubernetes Incident Recovery`

- **Technical / Cluster State:**
  - Cluster `proofix-case-01` namespace active; the VirtualService routes checkout traffic to subset `v2`, while the DestinationRule and ready pods expose only `v1`.

---

### Scene 2: The Baseline Gap — Recovery Without Proof
**Timecode:** `0:45 - 1:30` (Duration: 45 seconds)

```
+-------------------------------------------------------------------------------+
| VISUAL LAYOUT (Split Screen 50/50)                                            |
| LEFT (Red Border): Standard ReAct Baseline (GPT-5.6 / Gemini 3.7)             |
| RIGHT (Blue Border): ProofFix Autonomous Engine                               |
| CENTER OVERLAY: Real-time Grafana Error Rate & Latency Dashboards             |
+-------------------------------------------------------------------------------+
```

- **Voiceover Narration (`0:45 - 1:30`):**
  > *"Let’s watch a standard ReAct baseline and ProofFix tackle the exact same frozen Istio routing incident under 1,000 requests per window.*
  >
  > *On the left, the ReAct baseline inspects the VirtualService and patches its route from the undefined `v2` subset to `v1`. Traffic comes back and all three SLO windows pass.*
  >
  > *But strict recovery is more than green traffic. The baseline exhausts its step budget without tying its critical conclusion to the exact observations and SLO evidence in its ledger. It recovers the service, yet fails Verified Recovery Success on evidence closure.*
  >
  > *That distinction is the point of this benchmark: ProofFix is measured on safe, auditable recovery—not on whether it happened to issue a useful command."*

- **On-Screen Callouts:**
  - `LEFT: ReAct — Traffic Recovered, Evidence Chain Open`
  - `SLO: PASS | Semantic Verification: PASS | Evidence Closure: FAIL`
  - `CASE-01 RESULT: ReAct 0/3 VRS | ProofFix 3/3 VRS`

- **Technical / Cluster State:**
  - Baseline trial 1 records `disposition: recovered`, three healthy SLO samples, and `vrs.passed: false` with the sole failure reason `evidence_closure`.

---

### Scene 3: Inside ProofFix — The Nine-Stage Evidence-Closed Engine
**Timecode:** `1:30 - 2:45` (Duration: 75 seconds)

```
+-------------------------------------------------------------------------------+
| VISUAL LAYOUT (Full Screen Animated Architecture)                             |
| - Interactive 9-Stage State Machine Diagram highlighting active execution:    |
|   [1. Scope] -> [2. Observe] -> [3. Hypothesize] -> [4. Discriminate] ->     |
|   [5. Plan] -> [6. Safety Gate] -> [7. Execute] -> [8. Verify] -> [9. Close]  |
| - Live Cryptographic Hash Ledger (SHA-256 Chain) streaming in lower pane      |
+-------------------------------------------------------------------------------+
```

- **Voiceover Narration (`1:30 - 2:45`):**
  > *"Now watch how ProofFix handles the incident. It doesn't guess—it operates through a deterministic nine-stage state machine.*
  >
  > *Stage 1 binds the incident scope and creates an append-only, SHA-256 hash-chained ledger. Every single observation and action is cryptographically anchored.*
  >
  > *Stage 2 performs structured, read-only observation. It strips volatile server noise, tags every resource with a content digest, and redacts Secrets at the boundary—replacing credentials with SHA-256 hashes so zero passwords ever enter LLM context.*
  >
  > *In Stage 3 and 4, instead of latching onto the first explanation, ProofFix generates competing hypotheses and checks the VirtualService, DestinationRule, pods, and endpoints. The evidence proves that traffic targets `v2`, while only `v1` exists and has ready endpoints.*
  >
  > *In Stage 5 and 6, the planner formulates the minimal reversible fix: patch only `virtualservice/checkout` from subset `v2` to `v1`, paired with the exact inverse patch. The deterministic safety gate checks namespace scope, operation allowlisting, and rollback completeness.*
  >
  > *Only then does Stage 7 execute the patch in the sandbox."*

- **On-Screen Callouts:**
  - `9-STAGE STATE MACHINE: Scope -> Observe -> Hypothesize -> Discriminate -> Plan -> Approve -> Execute -> Verify -> Close`
  - `SECRET PRIVACY: In-Cluster Redaction & Cryptographic Digests`
  - `DETERMINISTIC SAFETY GATE: Mandatory Executable Rollback & Data-Loss Protection`

- **Technical / Cluster State:**
  - ProofFix ledger logs: `scope_decision`, `observation_collected (16 resources)`, `hypotheses_ranked (confidence: 0.85)`, `observation_collected (diagnostic test)`, `plan_proposed`, `policy_decision (allowed: true)`.

---

### Scene 4: Live Showdown & The Incident Recovery Packet
**Timecode:** `2:45 - 4:00` (Duration: 75 seconds)

```
+-------------------------------------------------------------------------------+
| VISUAL LAYOUT (Split Screen: Live Terminal & Rendered Document)               |
| LEFT: Live Multi-Window Verification Probes streaming (3000 total requests)   |
| RIGHT: Formatted Incident Recovery Packet (Markdown / Rendered PDF)           |
+-------------------------------------------------------------------------------+
```

- **Voiceover Narration (`2:45 - 4:00`):**
  > *"Here is the critical difference: ProofFix does not declare success when the patch applies. It enters Stage 8: Live Multi-Window Verification.*
  >
  > *ProofFix probes the live service across **three consecutive 10-second observation windows**, sending 1,000 real HTTP requests per window under continuous background load. It strictly enforces our preregistered SLO: HTTP 5xx rate strictly less than 0.001, and p95 latency strictly under 200 milliseconds.*
  >
  > *In measured trial 1: Window 1 has zero errors and p95 11.6 milliseconds. Window 2: zero errors, p95 10.1. Window 3: zero errors, p95 11.4. Workload readiness remains true.*
  >
  > *If any window had failed, ProofFix’s automated rollback engine would have immediately reverted the patch.*
  >
  > *Finally, in Stage 9, ProofFix compiles the Incident Recovery Packet. Every critical claim references exact hashed observations: ready `v1` pods and endpoints, the VirtualService patch result, and all three SLO windows.*
  >
  > *This is a production-grade artifact an on-call engineer can sign with total confidence."*

- **On-Screen Callouts:**
  - `MULTI-WINDOW VERIFICATION: Window 1 PASS | Window 2 PASS | Window 3 PASS`
  - `SLO CONJUNCTION: 5xx Rate = 0.000 (< 0.001) | p95 = 10.1–11.6ms (< 200ms)`
  - `DELIVERABLE: Signed Incident Recovery Packet with Cryptographic Audit Trail`

- **Technical / Cluster State:**
  - `artifacts/runs/case-01-proofix-t1-20260829T183615Z/result.json` records `vrs.passed: true`, `disposition: "recovered"`, and `evidence_closed: true`.

---

### Scene 5: The 15-Case Benchmark & Reproducibility
**Timecode:** `4:00 - 4:35` (Duration: 35 seconds)

```
+-------------------------------------------------------------------------------+
| VISUAL LAYOUT (Full Screen Matrix Display)                                    |
| - 15-Case Benchmark Suite Grid categorized by failure domain:                 |
|   Routing (3) | Scheduling (3) | Resource (2) | Auth (2) | Messaging (2) |    |
|   Storage (2) | Abstention Control (1)                                        |
| - Clean-room reproduction terminal executing `proofix verify-trace`           |
+-------------------------------------------------------------------------------+
```

- **Voiceover Narration (`4:00 - 4:35`):**
  > *"ProofFix is evaluated across an authoritative 15-case benchmark suite covering routing mismatches, CoreDNS cascades, scheduling deadlocks, Java OOMs, CPU throttling, RBAC deficits, Secret desynchronization, Kafka partition loss, and StorageClass failures.*
  >
  > *Crucially, CASE-15 is a healthy-system distractor control. When faced with noisy historical warnings on a healthy cluster, ProofFix proves its safety by making zero mutations and explicitly abstaining.*
  >
  > *The frozen matrix contains exactly 90 valid runs and 45 paired comparisons. ProofFix reached 37.8% strict VRS versus 26.7% for ReAct: an 11.1-point lift. The confidence interval includes zero and p equals 0.125, so we present this as a promising measured improvement—not a statistically conclusive win. Every one of the 90 selected trajectories passes hash-chain verification."*

- **On-Screen Callouts:**
  - `15 AUTHORITATIVE CASES: 14 Live Fault Challenges + 1 Abstention Control`
  - `90 PAIRED RUNS: 3 Independent Trials x 2 Systems x 15 Scenarios`
  - `VRS: 26.7% ReAct -> 37.8% ProofFix (+11.1 pp)`
  - `90/90 SELECTED TRAJECTORIES VERIFIED | 2,697 HASHED EVENTS`

- **Technical / Cluster State:**
  - Terminal executes `PYTHONPATH=src pytest tests/` (100% passing) and `proofix verify-trace` displaying valid hash-chain integrity.

---

### Scene 6: The Hot Take & Closing Call to Action
**Timecode:** `4:35 - 5:00` (Duration: 25 seconds)

```
+-------------------------------------------------------------------------------+
| VISUAL LAYOUT (Cinematic Typography & Live System Summary)                    |
| - Bold center headline:                                                       |
|   "ROOT-CAUSE ACCURACY IS A VANITY METRIC.                                    |
|    THE TRUE MEASURE OF AGENT RELIABILITY IS A VERIFIED STATE TRANSITION."     |
| - Final project links: GitHub Repository, REPRODUCTION.md, Decision PDF       |
+-------------------------------------------------------------------------------+
```

- **Voiceover Narration (`4:35 - 5:00`):**
  > *"Here is our core insight: **Root-cause accuracy is a vanity metric when you need a safe recovery.** Better prompts might generate eloquent diagnoses, but they cannot replace a closed-loop control system.*
  >
  > *The meaningful unit of AI reliability in engineering is a **verified state transition**: evidence closed, action admissible, blast radius bounded, and recovery proven under load.*
  >
  > *Don't trust the diagnosis. Trust the proof of recovery.*
  >
  > *Thank you."*

- **On-Screen Callouts:**
  - `DON'T TRUST THE DIAGNOSIS. TRUST THE PROOF OF RECOVERY.`
  - `ProofFix — micro1 Frontier Engineering Challenge 2026`
  - `Inspect the Codebase & Reproduction Guide: REPRODUCTION.md`

---

## Technical Demonstration Verification Matrix

This storyboard directly reflects the verified implementation in the ProofFix repository:

| Capability Shown | Implementation Source | Verification Test / Script |
|---|---|---|
| 9-Stage State Machine | `src/proofix/workflow.py` | `tests/test_workflow.py` |
| ReAct Baseline Comparison | `src/proofix/baseline.py` | `tests/test_baseline.py` |
| Deterministic Safety Policy | `src/proofix/policy.py` | `tests/test_policy.py` |
| Cryptographic Secret Redaction | `src/proofix/kubernetes.py` | `tests/test_kubernetes.py` |
| Multi-Window SLO Prober | `src/proofix/kubernetes.py` | `tests/test_kubernetes.py` |
| Append-Only Hash Chain Ledger | `src/proofix/trace.py` | `tests/test_trace.py` |
| SQLite DAG Coordinator | `src/proofix/dag.py` | `tests/test_dag.py` |
| Paired Statistics Engine | `src/proofix/stats.py` | `tests/test_stats.py` |
| Authoritative 15-Case Manifests | `benchmark/cases/CASE-01..15.json` | `tests/test_cases.py` |
| Live Fixture Lifecycles | `fixtures/CASE-01..15/*.sh` | `fixtures/CASE-XX/smoke.sh` |
