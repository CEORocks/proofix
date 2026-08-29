# CASE-10: database password rotation and application Secret desynchronization

This isolated fixture runs a real PostgreSQL 16.4 database, a billing HTTP API,
and a PostgreSQL client sidecar that continuously executes authenticated
`SELECT 1` probes. Injection uses a Kubernetes Job to rotate the database role,
updates the authoritative `db-credentials` Secret, and deliberately leaves the
billing pod on its stale environment-variable generation. The API returns 503
only after the real SQL authentication probe is rejected.

No script, pod, Job, or verifier prints decoded credentials. Evidence is limited
to SHA-256 generation fingerprints, Secret resource versions, references, and
authentication outcomes. Images are digest-pinned. Secrets are generated at
runtime in mode-0700 temporary storage and removed on script exit.

`install.sh` recreates only the explicitly ephemeral `proofix-case-10` namespace
to guarantee a clean database and deterministic credential generation. Do not put
real data in this fixture namespace. The service uses NodePort `30080`.

```bash
cd fixtures/CASE-10
./smoke.sh | tee case-10-smoke.log
```

From another host, export `PROOFIX_BASE_URL=http://K3S_NODE_IP:30080`.
Individual lifecycle commands are `install.sh`, `inject.sh`, `verify.sh fault`,
`reset.sh`, `verify.sh recovered`, and `rollback-recovery.sh`. Recovery copies the
authoritative generation to the billing Secret and performs a controlled rollout;
rollback restores the preserved stale generation without rotating the database.

Recovered verification requires a successful live credential Job and exactly
three consecutive HTTP windows with 5xx rate `< 0.001`, p95 `< 200ms`, and zero
non-200 responses.
