# ProofFix: Clean-Room Reproduction & Verification Guide

> **Authoritative instructions for deterministic clean-room setup, unit verification, DAG task coordination, fixture smoke testing, and full live paired benchmark execution.**

This document specifies the exact prerequisites, environment assumptions, step-by-step verification commands, and artifact output locations for the ProofFix repository. Following these instructions supports deterministic clean-room verification; live timings and model outputs can still vary with network, registry, and model-service conditions.

---

## Table of Contents

1. [Hardware, OS, and Software Prerequisites](#1-hardware-os-and-software-prerequisites)
2. [Cluster & Host Environment Assumptions](#2-cluster--host-environment-assumptions)
   - [Single-Node k3s Baseline](#single-node-k3s-baseline)
   - [Remote Runner (vultr-1 / Runner Nodes) & SSH Setup](#remote-runner-vultr-1--runner-nodes--ssh-setup)
   - [Kernel & cgroup v2 Requirements](#kernel--cgroup-v2-requirements)
   - [Special Scenario Dependencies (Istio, Kafka, StorageClass)](#special-scenario-dependencies-istio-kafka-storageclass)
3. [Deterministic Clean-Room Installation](#3-deterministic-clean-room-installation)
4. [Step-by-Step Verification Phases](#4-step-by-step-verification-phases)
   - [Phase 1: Unit & Case Contract Verification](#phase-1-unit--case-contract-verification)
   - [Phase 2: Cryptographic Trace Ledger Verification](#phase-2-cryptographic-trace-ledger-verification)
   - [Phase 3: Paired Statistical Engine Verification](#phase-3-paired-statistical-engine-verification)
   - [Phase 4: SQLite-Backed DAG Coordinator Verification](#phase-4-sqlite-backed-dag-coordinator-verification)
   - [Phase 5: Standalone Fixture Lifecycle & Smoke Verification](#phase-5-standalone-fixture-lifecycle--smoke-verification)
   - [Phase 6: Single-Case Live Paired Trial](#phase-6-single-case-live-paired-trial)
   - [Phase 7: Full 90-Run Paired Matrix Orchestration](#phase-7-full-90-run-paired-matrix-orchestration)
5. [Exact Artifact Locations & Schema Layout](#5-exact-artifact-locations--schema-layout)
6. [Infrastructure Failure vs. Agent Failure Classification](#6-infrastructure-failure-vs-agent-failure-classification)

---

## 1. Hardware, OS, and Software Prerequisites

A clean-room environment requires the following specifications:

- **Operating System:** Linux (Ubuntu 22.04 LTS, Ubuntu 24.04 LTS, or Debian 12 recommended). x86_64 or aarch64.
- **Compute & Memory:**
  - Minimum for Control Plane & Standard Cases: 4 vCPUs, 8 GiB RAM, 30 GiB available disk.
  - Recommended for full Kafka / Java Heap cases (CASE-11, CASE-12): 8 vCPUs, 16 GiB RAM, 50 GiB SSD.
- **Host Packages:**
  ```bash
  sudo apt-get update && sudo apt-get install -y \
    python3 python3-venv python3-pip \
    curl git rsync openssh-client openssh-server \
    jq sqlite3
  ```
- **Kubernetes Client:** `kubectl` v1.28.0+ installed on the host search path.
- **Model CLI Backends (One of the following):**
  - **Google Antigravity CLI (`agy`):** Pinned model `gemini-3.7-flash-medium`.
  - **OpenAI Codex CLI (`codex`):** Pinned model `gpt-5.6-sol`.

---

## 2. Cluster & Host Environment Assumptions

### Single-Node k3s Baseline

The primary evaluation target for CASE-02 through CASE-12, CASE-14, and CASE-15 is a standard, dedicated single-node k3s cluster.

- **Installation Command on the Node:**
  ```bash
  curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 644
  ```
- **Kubeconfig Location:** `/etc/rancher/k3s/k3s.yaml` (default in `src/proofix/runner.py` and `scripts/`).
- **Default StorageClass:** `rancher.io/local-path` (pre-installed by default in k3s).
- **NodePort Range:** Dedicated NodePorts in range `30072`–`30115` must be unallocated and accessible on the cluster host interface.

### Remote Runner (`vultr-1` / Runner Nodes) & SSH Setup

When executing benchmark runs from a central control plane against dedicated runner VMs (e.g. `vultr-1`, `node1`, or specific worker IPs specified in `benchmark/environments.json`):

1. **SSH Keyless Authentication:** The control machine must possess passwordless SSH access to the runner host:
   ```bash
   ssh -o BatchMode=yes <runner-host> "kubectl get nodes"
   ```
2. **Kubeconfig Environment:** The remote user must have read access to `/etc/rancher/k3s/k3s.yaml` or set `export KUBECONFIG=/path/to/k3s.yaml`.
3. **Local Standalone Mode:** If running directly on the k3s host or routing via kubectl port-forwarding without SSH, specify `--localize-host` or `--host local`.

### Kernel & cgroup v2 Requirements

- **Unified cgroup hierarchy (cgroup v2):** Required for `CASE-07` (Java Heap cgroup OOM) and `CASE-08` (CPU CFS quota throttling).
- Verify on the cluster host:
  ```bash
  stat -fc %T /sys/fs/cgroup/
  # Expected output: cgroup2fs
  ```

### Special Scenario Dependencies (Istio, Kafka, StorageClass)

- **CASE-01 (Istio Routing):** Requires Istio 1.30.4+ installed with sidecar auto-injection support on the cluster.
- **CASE-11 & CASE-12 (Kafka Messaging):** Uses digest-pinned `redpanda/redpanda:v25.3.8`. Requires `mirror.gcr.io` / Docker Hub access for the initial image pull.
- **CASE-13 (PVC Multi-Attach Challenge):**
  - Requires a multi-node cluster (2+ Ready nodes) with an attach-required CSI driver.
  - The frozen run used k3s v1.36.4+k3s1 with Longhorn v1.11.3 and a one-replica `longhorn-single` StorageClass across two temporary Vultr nodes.
  - Set `export PROOFIX_CASE13_STORAGE_CLASS=longhorn-single` for that self-managed topology, or use an equivalent cloud block StorageClass such as GCE PD `standard-rwo`.
  - On single-node k3s using `local-path`, `inject.sh` safely returns `UNSUPPORTED_INFRASTRUCTURE` without mutating pods.
- **CASE-14 (StorageClass Provisioner):** Recreates pending claims using `rancher.io/local-path` (or `PROOFIX_GOOD_STORAGE_CLASS`).

---

## 3. Deterministic Clean-Room Installation

Execute the following commands from the repository root:

```bash
# 1. Clean environment checkout
git status

# 2. Initialize isolated virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Upgrade pip and build tools
pip install --upgrade pip setuptools wheel

# 4. Install ProofFix package in editable development mode
pip install -e '.[dev]'

# 5. Verify CLI registration
proofix --help
```

---

## 4. Step-by-Step Verification Phases

### Phase 1: Unit & Case Contract Verification

Run the full automated test suite to verify the state machine, safety policy, DAG engine, cryptographic ledger, statistics module, and authoritative case manifests:

```bash
# Run all unit tests
PYTHONPATH=src pytest tests/ -v

# Specifically test the 15-case benchmark contract manifests
PYTHONPATH=src pytest tests/test_cases.py -v
```

*Expected Result:* All tests pass with zero warnings and zero failures. `test_cases.py` validates that all 15 JSON manifests (`CASE-01.json` through `CASE-15.json`) adhere strictly to schema types, immutable titles, category bindings, fixed SLO objects, and data-loss protection markers.

### Phase 2: Cryptographic Trace Ledger Verification

Test the append-only SHA-256 hash-chain verification tool:

```bash
PYTHONPATH=src pytest tests/test_trace.py -v
```

You can verify any generated run trace file at any time using the `proofix` CLI:
```bash
proofix verify-trace artifacts/runs/<run_id>/trajectory.jsonl
# Expected output: {"path": "...", "reason": "ok", "valid": true}
```

### Phase 3: Paired Statistical Engine Verification

Verify the bootstrap paired confidence intervals and exact McNemar test computations:

```bash
PYTHONPATH=src pytest tests/test_stats.py -v
```

To summarize an existing benchmark result JSONL file:
```bash
# Example synthetic validation
cat << 'JSON_EOF' > /tmp/test_summary.json
[
  {"baseline_passed": false, "proofix_passed": true},
  {"baseline_passed": false, "proofix_passed": true},
  {"baseline_passed": true, "proofix_passed": true}
]
JSON_EOF

proofix summarize /tmp/test_summary.json
rm -f /tmp/test_summary.json
```

### Phase 4: SQLite-Backed DAG Coordinator Verification

Verify the transaction-isolated, multi-worker DAG coordinator (`src/proofix/dag.py` and `scripts/coordinator.py`):

```bash
# 1. Run automated DAG coordinator tests
PYTHONPATH=src pytest tests/test_dag.py -v

# 2. Initialize the SQLite coordinator database
python3 scripts/coordinator.py --db state/coordinator.db init

# 3. Submit a test task batch
cat << 'JSON_EOF' > /tmp/dag_tasks.json
[
  {"id": "task-observe", "payload": {"stage": "observe"}, "max_attempts": 3},
  {"id": "task-plan", "depends_on": ["task-observe"], "payload": {"stage": "plan"}, "max_attempts": 3}
]
JSON_EOF
python3 scripts/coordinator.py --db state/coordinator.db submit-json /tmp/dag_tasks.json

# 4. Inspect status
python3 scripts/coordinator.py --db state/coordinator.db status

# 5. Claim a runnable task
python3 scripts/coordinator.py --db state/coordinator.db claim --owner worker-1 --lease-seconds 60

# 6. Complete task
python3 scripts/coordinator.py --db state/coordinator.db complete task-observe --owner worker-1 --result-json '{"status": "observed"}'

# 7. Clean up scratch file
rm -f /tmp/dag_tasks.json
```

### Phase 5: Standalone Fixture Lifecycle & Smoke Verification

Each of the 15 benchmark scenarios includes an authoritative, self-contained shell fixture in `fixtures/CASE-XX/`. To verify a scenario's complete lifecycle manually on the k3s host:

```bash
# Example: CASE-07 (Java Heap OOM Exit 137)
cd fixtures/CASE-07
./install.sh              # Deploys pricing-api with -Xmx128m (Healthy SLO verification)
./inject.sh               # Injects -Xmx512m under 256Mi container limit (Causes cgroup OOM)
./verify.sh fault         # Verifies real OOMKilled / Exit 137 status and 503 response
./reset.sh                # Applies accepted minimal reversible patch (-Xmx128m)
./verify.sh recovered     # Asserts 3 consecutive healthy SLO windows under traffic
./smoke.sh                # Runs the complete automated lifecycle end-to-end
cd ../..
```

### Phase 6: Single-Case Live Paired Trial

Execute a single end-to-end benchmark trial using the official runner harness (`scripts/run_live_case.py`).

**Running with Google Antigravity backend (`gemini-3.7-flash-medium`):**
```bash
python3 scripts/run_live_case.py \
  --case-path benchmark/cases/CASE-07.json \
  --system proofix \
  --trial 1 \
  --host local \
  --remote-fixture-dir fixtures/CASE-07 \
  --namespace proofix-case-07 \
  --workload-selector app.kubernetes.io/name=pricing-api \
  --node-port 30077 \
  --local-port 18107 \
  --probe-path /price \
  --backend antigravity \
  --model gemini-3.7-flash-medium \
  --verification-settle-seconds 5.0
```

**Running the Baseline ReAct Agent:**
```bash
python3 scripts/run_live_case.py \
  --case-path benchmark/cases/CASE-07.json \
  --system react \
  --trial 1 \
  --host local \
  --remote-fixture-dir fixtures/CASE-07 \
  --namespace proofix-case-07 \
  --workload-selector app.kubernetes.io/name=pricing-api \
  --node-port 30077 \
  --local-port 18107 \
  --probe-path /price \
  --backend antigravity \
  --model gemini-3.7-flash-medium \
  --verification-settle-seconds 5.0
```

### Phase 7: Full 90-Run Paired Matrix Orchestration

To rerun the complete frozen benchmark design (15 cases x 3 trials x 2 systems = 90 runs) across configured cluster hosts:

```bash
python3 scripts/run_matrix.py \
  --cases all \
  --trials 1,2,3 \
  --systems react,proofix \
  --backend antigravity \
  --model gemini-3.7-flash-medium \
  --seed 20260829
```

*Key Matrix Flags:*
- `--cases CASE-01,CASE-02`: Run a subset of cases.
- `--no-resume`: Disables automatic resumption and re-evaluates all pairs from zero.
- `--localize-host`: Overrides remote SSH host bindings to run locally against the current cluster.
- `--kubeconfig-override /path/to/k3s.yaml`: Forces a specific kubeconfig across all case workers.

---

## 5. Exact Artifact Locations & Schema Layout

Every live run produces an isolated, self-auditing directory under `artifacts/runs/<run_id>/`:

```
artifacts/
├── benchmark/
│   ├── results.jsonl             # Exactly 90 deduplicated valid scored rows
│   ├── summary.json              # Machine-readable paired metrics
│   └── SUMMARY.md                # Generated human-readable result table
├── diagnostics/
│   └── infrastructure-invalid.final.jsonl # Excluded invalid attempts
├── shards/final/                 # Immutable raw result streams from each runner
└── runs/
    └── <case_id>-<system>-t<trial>-<timestamp>/
        ├── config.json           # Frozen input configuration (LiveRunConfig)
        ├── fixture.json          # Raw output logs from fixture install/inject/verify/reset
        ├── initial-snapshot.json # Full cluster inventory before any agent action
        ├── trajectory.jsonl      # Append-only SHA-256 hash-chained execution events
        └── result.json           # Final structured outcome and VRS evaluation report
```

### Schema Descriptions

- **`config.json`**: Records the exact scenario path, system (`react` or `proofix`), trial index, host, ports, backend model name, and SLO parameters.
- **`initial-snapshot.json`**: A JSON array of all Kubernetes resource objects gathered at t0, indexed with cryptographic content digests.
- **`trajectory.jsonl`**: Each line contains an append-only event committing to `previous_hash` with `event_hash`:
  ```json
  {
    "schema_version": "1.0",
    "run_id": "case-07-proofix-t1-20260829T000000Z",
    "sequence": 0,
    "timestamp": "2026-08-29T00:00:00.000000+00:00",
    "stage": "scope",
    "event_type": "run_started",
    "sources": [],
    "payload": { "case_id": "CASE-07", "system": "proofix" },
    "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
    "event_hash": "a1b2c3..."
  }
  ```
- **`result.json`**: Emits top-level boolean `valid`, `elapsed_seconds`, `outcome` (disposition, action count, SLO samples, evidence closure), and `vrs` (conjunctive check results: `live_recovery`, `safety`, `three_consecutive_slo_windows`, `action_budget`, `trace_integrity`, `fixture_semantic_verification`, `evidence_closure`).

---

## 6. Infrastructure Failure vs. Agent Failure Classification

To preserve scientific fairness, ProofFix enforces a strict boundary between infrastructure faults and valid agent evaluation outcomes:

| Classification | Failure Cause / Signature | Evaluator Protocol |
|---|---|---|
| **Agent Failure (Valid Trial)** | Model hallucinates invalid resource; policy rejects forbidden operation; SLO fails after remediation; step budget exhausted. | Trial recorded as `valid: true`, `passed: false`. Scored as `VRS = 0`. Retries strictly forbidden. |
| **Infrastructure Invalid (Void Trial)** | SSH tunnel timeout; node power loss; host out of disk; image pull registry rate limit; missing multi-node CSI on single-node k3s. | Trial recorded as `valid: false`, `infrastructure_error: "..."` and preserved separately. The distributed recovery harness resumed missing valid keys while retaining already valid counterparts. This is a disclosed deviation from the original complete-pair rerun rule. |

### Rebuild the frozen aggregate

```bash
PYTHONPATH=src python3 tools/aggregate_results.py \
  --input artifacts/shards/final/vm2/results.raw.jsonl \
  --input artifacts/shards/final/node1/results.raw.jsonl \
  --input artifacts/shards/final/vm4/results.raw.jsonl \
  --input artifacts/shards/final/vm5/results.raw.jsonl \
  --runs-root artifacts/runs \
  --results artifacts/benchmark/results.jsonl \
  --invalid artifacts/diagnostics/infrastructure-invalid.final.jsonl \
  --summary-json artifacts/benchmark/summary.json \
  --summary-md artifacts/benchmark/SUMMARY.md
```

Expected final verification: `valid_runs=90`, `verified_trajectories=90`, and `events=2697`.
