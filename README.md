# ProofFix

> Don't trust the diagnosis. Trust the proof of recovery.

ProofFix is an evidence-closed Kubernetes incident recovery agent built for the
micro1 Frontier Engineering Challenge 2026. It investigates an incident,
actively challenges its leading hypothesis, proposes the smallest reversible
recovery, enforces deterministic safety policy, executes only in a sandbox,
and verifies whole-system service-level objectives before declaring success.

The implementation and measured benchmark are in progress. Until live cluster
results exist, no recovery-rate claim in this repository should be treated as
measured evidence.

## Development

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest
```

See `report-source.md` and the verified decision brief under `output/pdf/` for
the approved problem definition and evaluation plan.

