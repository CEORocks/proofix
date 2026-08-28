# ProofFix: Winning Problem Definition and Execution Plan

**Audience:** Hackathon owner / engineering lead  
**Decision date:** 28 August 2026  
**Competition:** micro1 Frontier Engineering Challenge 2026  
**Decision:** Build **ProofFix**, an evidence-closed Kubernetes incident recovery agent for on-call SREs.

## Direct executive answer

The strongest winning problem is the last mile of cloud incident response: an on-call engineer may receive a plausible AI diagnosis, but still cannot safely act because the AI has not established the causal evidence chain, selected a valid recovery action, bounded blast radius, or proved that service health returned.

ProofFix will move from alert to a human-approvable **Incident Recovery Packet** and, in a disposable Kubernetes sandbox, execute and verify the proposed recovery. Its primary benchmark is **Verified Recovery Success (VRS)** across 15 paired cases: all 14 current AIOpsLab mitigation scenarios plus one noisy no-op control. Baseline and full system use the same model, scenario, action interface, 20 environment-action limit, total token budget, and clean cluster. Each is run three times per case.

The central product promise is: **do not trust a diagnosis; trust a verified state transition with evidence.**

## Why this problem wins the rubric

| Candidate | User value /15 | Agentic fit /30 | End-to-end /20 | Benchmark /15 | Repro /15 | Insight /5 | Decision score |
|---|---:|---:|---:|---:|---:|---:|---:|
| ProofFix: verified Kubernetes recovery | 15 | 28 | 19 | 15 | 14 | 5 | **96** |
| CI/test-failure repair agent | 13 | 23 | 18 | 15 | 15 | 3 | 87 |
| Kubernetes compliance evidence agent | 14 | 25 | 17 | 13 | 12 | 4 | 85 |
| FinOps anomaly remediation agent | 14 | 24 | 16 | 12 | 11 | 4 | 81 |

These are rubric-ceiling estimates, not measured project results. ProofFix leads because it combines a high-stakes but safely sandboxable user problem, purposeful multi-stage agent engineering, a professional operational artifact, a binary end-to-end oracle, 10+ licensed live scenarios, and a memorable failure-derived insight. CI repair is easier to grade but crowded. Compliance introduces interpretation and qualified-review burden. FinOps has strong value but weaker live recovery oracles in the available public datasets.

## Evidence that the bottleneck is real

- [Google SRE's troubleshooting methodology](https://sre.google/sre-book/effective-troubleshooting/) describes incident work as iterative hypothesis testing against confirming and disconfirming evidence, followed by controlled treatment and observation. It also emphasizes preserving evidence and documenting tests and state changes.
- [Google SRE's emergency-response guidance](https://sre.google/sre-book/introduction/) identifies restoration time as the relevant emergency-response measure and reports roughly a threefold MTTR improvement from practiced playbooks versus improvisation.
- [ITBench](https://arxiv.org/abs/2502.05352) reported that state-of-the-art agents resolved only 13.8% of its SRE scenarios, despite using realistic IT automation tasks.
- [Cloud-OpsBench](https://arxiv.org/abs/2603.00468) contains 754 runtime-verified cloud RCA cases. Across ten agents, the best joint RCA accuracy reached 0.76/0.68 on its two systems while evidence closure was only 0.38/0.15. Correct answers therefore overstate usable diagnostic quality.
- [A 1,675-run failure study](https://arxiv.org/abs/2602.09937) found that hallucinated telemetry interpretation and incomplete exploration persist across model tiers; prompt engineering alone did not resolve the dominant pitfalls.
- [R2Act](https://arxiv.org/abs/2607.04623) found 91.4%-99.7% root-service accuracy for the strongest RAG systems but only 36.8%-60.3% recovery-action validity. Even with a correct diagnosis, invalid actions remained common.
- A [trajectory-level study published 21 August 2026](https://arxiv.org/abs/2608.21310) found that successful investigations stay on the fault-impact surface, act on retrieved evidence, and broaden queries as investigation deepens; final-answer scoring hides these process failures.

## Target user and exact bottleneck

**Primary user:** the on-call SRE or platform engineer at a small or mid-sized organization running Kubernetes microservices, especially when the responder is not the service author.

**Trigger:** an availability or latency alert arrives with noisy, distributed evidence across Kubernetes objects/events, logs, metrics, traces, deployment configuration, and service dependencies.

**Current bottleneck:** the responder must decide, under time pressure, whether a diagnosis is supported, which action is admissible, what could be damaged, how to roll back, and whether the system actually recovered. A direct prompt can produce a persuasive answer without doing this work.

**Job to be done:** “Give me the smallest safe recovery I can approve now, show the evidence that justifies it, and prove the service is healthy afterward.”

**User-facing output:** a signed-quality Incident Recovery Packet containing incident summary, affected SLO, evidence timeline, dependency/fault path, considered and rejected hypotheses, proposed action and exact target, risk/blast-radius assessment, approval checkpoint, before/after health checks, rollback plan, and residual uncertainty.

## Baseline and full workflow

### Simple baseline

A single general-purpose ReAct agent receives the official AIOpsLab mitigation task and basic operating instructions. It has the same model snapshot, typed AIOpsLab APIs, 20 environment actions, total token budget, wall-clock limit, and fresh cluster as ProofFix. It can inspect telemetry and modify the sandbox, but has no explicit evidence ledger, hypothesis board, policy gate, specialized verification, runbook memory, or post-recovery state machine.

### ProofFix workflow

1. **Deterministic incident controller** creates a run ID, freezes the scenario manifest, enforces budgets, and records every state transition.
2. **Observer** uses read-only tools to establish topology, symptoms, recent changes, and candidate fault surfaces. Every observation receives a source pointer and timestamp.
3. **Hypothesis manager** maintains ranked hypotheses with predicted observations, supporting evidence, counterevidence, and the next discriminating test.
4. **Evidence challenger** tries to falsify the leading diagnosis, detects unsupported claims, requires all case-specific evidence gates, and can send the workflow back to observation.
5. **Recovery planner** proposes the smallest reversible action, exact target, expected postcondition, blast radius, and rollback. It retrieves only versioned runbooks and development-set failure lessons.
6. **Deterministic safety gate** checks an allowlist, target scope, namespace, command shape, data-loss risks, and rollback availability. In a production path, a qualified human must approve here. In the benchmark, execution remains inside a disposable cluster.
7. **Sandbox executor** applies one approved action plan and records the diff and return values.
8. **Health verifier** runs whole-environment checks, service probes, error-rate/latency checks, and persistence checks. Failure triggers rollback or one bounded re-plan.
9. **Report compiler** turns the trace into the Incident Recovery Packet and a machine-readable result. It does not invent evidence; every assertion links to a tool result.

### Purposeful memory

- **Working memory:** hypothesis/evidence graph for the current incident.
- **Semantic memory:** pinned service topology, operational invariants, and approved runbooks.
- **Episodic memory:** failure lessons derived only from development scenarios. Evaluation case IDs and gold labels are excluded to prevent leakage.

## Fifteen-case benchmark

The benchmark uses the current MIT-licensed [AIOpsLab](https://github.com/microsoft/AIOpsLab) live testbed. Its mitigation evaluator inspects the health of the whole system after recovery, not merely the injected resource. The first 14 cases are already registered mitigation tasks; case 15 is our pre-registered safety control.

| # | Case | Fault family | What it tests |
|---:|---|---|---|
| 1 | Target-port mismatch: user service | Kubernetes routing | YAML inspection and target precision |
| 2 | Target-port mismatch: text service | Kubernetes routing | Same mechanism, different topology/blast radius |
| 3 | Target-port mismatch: post-storage | Kubernetes routing | Downstream persistence dependency |
| 4 | Missing MongoDB authentication | Authorization/config | Credential/config evidence without secret leakage |
| 5 | Revoked MongoDB auth: geo | Authorization | Symptom-to-backend propagation |
| 6 | Revoked MongoDB auth: rate | Authorization | Transfer across service target |
| 7 | Unregistered MongoDB user: geo | Identity/config | Distinguish absent user from revoked rights |
| 8 | Unregistered MongoDB user: rate | Identity/config | Topology transfer and exact target |
| 9 | Hotel application misconfiguration | Application config | Cross-layer diagnosis and reversible fix |
| 10 | Social deployment scaled to zero | Capacity/deployment | Restore service with minimal change |
| 11 | Assigned to nonexistent node | Scheduling | Counterfactual scheduling evidence |
| 12 | Astronomy Shop Kafka queue failure | Messaging/backpressure | Multi-signal, multi-service propagation |
| 13 | Redeploy without persistent volume | Data safety | **Challenge case:** recover without masking data-loss risk |
| 14 | Wrong binary usage | Runtime/operation | Process and image inspection |
| 15 | Healthy system with noisy distractors | Safety/abstention | **Control:** correct outcome is no consequential action |

### Pre-registered primary metric

For case *i*, **VRS_i = 1** only if all conditions hold:

1. the workflow submits within its action/time/token budget;
2. AIOpsLab's whole-environment evaluator confirms recovery (or unchanged health for the no-op case);
3. no forbidden or out-of-scope action occurred;
4. required post-recovery probes pass for the fixed observation window; and
5. the final packet contains no unsupported critical claim.

**Verified Recovery Success = mean(VRS_i)** across all case-trial pairs. This conjunction prevents a lucky fix, unsafe fix, or eloquent but unverified diagnosis from scoring as success.

### Secondary metrics

- Time to mitigate (median and p90)
- Evidence-gate completion and unsupported-claim rate
- Invalid/forbidden action rate and safe-abstention accuracy
- Environment actions, model tokens, runtime, and estimated cost per case
- Recovery action precision (operation + target)
- Rollback success where invoked
- Human review time on five blinded Incident Recovery Packets, if a qualified reviewer is available

### Experimental design

- 15 cases x 3 independent trials x 2 systems = **90 total runs**.
- Paired clean environments from one pinned image; baseline/full run order alternates by case and trial.
- Temperature 0 where supported; fixed model version, 20 environment actions, equal total token ceiling, identical timeouts, no internet during evaluation.
- Pre-register case manifest, metric code, acceptable/forbidden action policy, seeds, and exclusions before the final run.
- Report every run. No cherry-picking or best-of-N.
- Report absolute percentage-point improvement, paired bootstrap 95% confidence interval, and exact McNemar test for paired binary outcomes.
- Keep a fast deterministic replay mode from captured, self-generated fixtures and a full live-cluster mode. Judges can reproduce the main comparison quickly and replay three representative live recoveries.

### Target gates (goals, not results)

- VRS >= 80% and at least +30 percentage points over baseline
- Zero forbidden actions and 100% safe abstention on the no-op control
- >= 85% evidence-gate completion
- Median time to mitigate under 10 minutes
- Clean-room quick reproduction under 15 minutes; full benchmark under 2 hours on four runner VMs

## VM and research-tool execution plan

| Resource | Role | Guardrail |
|---|---|---|
| VM2 (current) | Control plane, repository, orchestration, trace ingestion, dashboard, result aggregation | No scenario runs compete with coordination services |
| Runner VM A | Baseline shards | Same immutable runner image as full system |
| Runner VM B | ProofFix shards | Pair/alternate with VM A to control machine bias |
| Runner VM C | Additional paired trials and live demo cluster | Disposable namespaces/clusters only |
| Clean-room VM | Setup from zero, quick/full reproduction, final video capture | No dev cache, no private credentials |
| Gemini Deep Research bridges | Build and verify the failure taxonomy and runbook source set; seek disconfirming evidence | Freeze versioned outputs before evaluation; no gold-label access |
| Antigravity pipelines | Deploy scenarios, inject faults, schedule paired runs, capture trajectories, retry infrastructure failures only | Never retry a valid agent failure; all pipeline config ships in repo |
| Frontier-model orchestration | Development ablations across models; fixed model for final fair comparison | Baseline and ProofFix use the same final model and total token ceiling |

Every run emits JSONL plus a human-readable trace: instructions, observations, tool calls and responses, hypothesis updates, verifier feedback, policy decision, approval checkpoint, action diff, health checks, retries, final packet, versions, timestamps, costs, and content hashes. Secrets are redacted at the tool boundary.

## Build and submission schedule

### Aug 28 - lock the foundation

- Freeze problem statement, metric, cases, fairness contract, licenses, and architecture.
- Scaffold repo, pinned environment, trace schema, baseline agent, and one AIOpsLab smoke case.
- Create changelog entry 0 before any agentic enhancement.

### Aug 29 - make one complete path excellent

- Implement observer, hypothesis/evidence ledger, typed tools, safety gate, executor, verifier, and packet compiler.
- Finish five development scenarios and record each failure mode.
- Add deterministic snapshot/replay fixture capture and basic operator UI/report.

### Aug 30 - earn the measured-improvement points

- Run ablations: baseline; +evidence ledger; +challenger; +safety policy; +post-action verifier; optional memory.
- Remove components that do not improve the pre-registered metric.
- Freeze code and run the 90 paired evaluations across runner VMs.
- Generate comparison tables, confidence intervals, changelog, and representative trajectories.

### Aug 31 - prove reproducibility and tell the story

- Run clean-room setup, quick benchmark, and three-case live replay from the reproduction guide.
- Finalize README, licenses, exact commands, expected outputs, runtime/cost, limitations, and trajectory viewer.
- Record <=5 minute video: user problem -> baseline failure -> one live ProofFix recovery -> benchmark -> changelog -> removed experiment -> hot take.
- Freeze by 15:00 UTC, leaving a submission buffer before the displayed 18:00 UTC event end. Verify the authenticated countdown and package fields before upload.

## Planned improvement changelog

| Stage | Hypothesis | Evidence to collect | Keep only if |
|---|---|---|---|
| Baseline | Generic ReAct can recover simple incidents | VRS, actions, TTM, failure taxonomy | Establishes fair starting point |
| Iteration 1 | Structured evidence ledger prevents premature diagnosis | VRS + evidence closure | Improves VRS/grounding without excessive latency |
| Iteration 2 | Counter-hypothesis verifier catches plausible wrong causes | Unsupported claims, invalid actions | Reduces harmful false certainty |
| Iteration 3 | Deterministic safety policy prevents target/operation mistakes | Forbidden-action rate | Reaches zero safety violations |
| Iteration 4 | Post-action health verification converts fixes into proved recovery | Whole-system health, rollback | Improves VRS and catches partial fixes |
| Iteration 5 | Failure memory improves transfer | Held-out VRS/cost | Helps unseen targets without label leakage |

At least one failed or removed experiment will be preserved. Likely candidates to test and remove are unconstrained multi-agent debate (high cost/latency) and unfiltered trajectory memory (anchoring/leakage risk).

## Risks and mitigations

- **“Another SRE agent” novelty risk:** position the contribution as evidence-closed, policy-gated, verified recovery—not chat-based RCA. The product unit is the recovery packet and verified state transition.
- **Live benchmark flakiness:** pair runs on pinned images, alternate order, repeat three times, separate infrastructure failures from valid agent failures, and ship deterministic replay fixtures.
- **Benchmark leakage:** development/evaluation split, freeze manifests, disable internet, exclude evaluation labels and golden trajectories from memory.
- **High action risk:** disposable clusters only, typed allowlist, namespace scope, data-loss policy, rollback, and production human approval gate.
- **Time risk:** deliver the baseline and one complete incident path first; UI polish follows only after the evaluator and trace are working.
- **License risk:** redistribute only dependencies/assets with verified compatible licenses. AIOpsLab is MIT. Cloud-OpsBench is used as research evidence only unless explicit repository licensing is verified.

## Hot take

**Root-cause accuracy is a vanity metric when the user needs a safe recovery.** The meaningful unit of agent reliability is a verified state transition: evidence closed, action admissible, blast radius bounded, recovery observed, and rollback available. Better prompts may improve prose; they do not supply the missing control system.

## Material limitations

- AIOpsLab is a benchmark, not production. Its faults and service topologies do not represent every operational incident.
- Fifteen cases support a strong hackathon comparison but not a universal reliability claim.
- A model may overfit recognizable scenario patterns; held-out target variants, no internet, and gold-label isolation reduce but do not eliminate this risk.
- Human review time is secondary and only reported if a qualified reviewer can evaluate blinded packets consistently.
- The HackerEarth dynamic detail tabs were inaccessible from this VM because the site rejected the anonymous/VPN IP. Detailed rules therefore come from the supplied 10-page rulebook; the public page was used for event dates, team size, registration count, and organizer identity.

## Claim-to-source ledger

| Claim family | Source | Publisher / date | URL / access note |
|---|---|---|---|
| Rubric, ground rules, deliverables, 10+ cases, <=5 minute video | *Agentic Workflows Hackathon* | micro1, supplied PDF created 27 Aug 2026 | Local source: `micro1 - First Hackathon97ce7c5.pdf`; all 10 pages inspected |
| Event dates, online, team size 1, 5.3K registrations | *Frontier Engineering Challenge 2026* | HackerEarth / accessed 28 Aug 2026 | https://www.hackerearth.com/community/challenges/hackathon/micro1-frontier-engineering-challenge-2026/ |
| Hypothesis testing, controlled treatment, evidence preservation | *Effective Troubleshooting* | Google SRE / accessed 28 Aug 2026 | https://sre.google/sre-book/effective-troubleshooting/ |
| Playbooks and emergency-response restoration metric | *Site Reliability Engineering*, Introduction | Google SRE / accessed 28 Aug 2026 | https://sre.google/sre-book/introduction/ |
| 13.8% SRE resolution and benchmark scope | *ITBench* | IBM et al., 7 Feb 2025 | https://arxiv.org/abs/2502.05352 |
| Live fault injection, whole-system evaluation, task taxonomy | *AIOpsLab* | Chen et al., 12 Jan 2025 | https://arxiv.org/abs/2501.06706 |
| Current MIT license and 14 mitigation registry entries | *microsoft/AIOpsLab* | Microsoft / accessed 28 Aug 2026 | https://github.com/microsoft/AIOpsLab |
| Outcome/evidence gap: JRA vs ECR | *Cloud-OpsBench* v2 | Wang et al., 22 Aug 2026 | https://arxiv.org/abs/2603.00468 |
| Prompt-only failure and 1,675 runs | *Why Do AI Agents Systematically Fail at Cloud RCA?* | Kim et al., 10 Feb 2026 | https://arxiv.org/abs/2602.09937 |
| Diagnosis/recovery-action gap | *Can LLMs Really Recover Microservice Failures?* | Qi et al., 6 Jul 2026 | https://arxiv.org/abs/2607.04623 |
| 3,500 trajectory study and evidence-grounded behavior | *Beyond Fault Localization* | Lu et al., 21 Aug 2026 | https://arxiv.org/abs/2608.21310 |

## Research stop condition

Research stopped after the decision survived a second-wave challenge on novelty, licensing, reproducibility, data availability, benchmark size, and action safety. Additional candidate searches were returning weaker variants of the same options and were unlikely to change the selection before implementation needed to begin.
