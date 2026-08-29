# CASE-09: ServiceAccount RBAC permission deficit

This fixture deploys a real `inventory-controller` ServiceAccount and a Java
controller that calls the live Kubernetes API for `inventory-settings`. Injection
replaces its namespace Role with rules that do not cover ConfigMaps; the endpoint
then reports 503 only because the API server returns Forbidden. Recovery grants
`get` only for the named ConfigMap and `list` for ConfigMaps in this namespace
(Kubernetes cannot combine `list` with `resourceNames`). It never grants Secrets,
cluster scope, `cluster-admin`, or a broader identity.

The digest-pinned service is exposed on NodePort `30079`. Run on a single-node
k3s host:

```bash
cd fixtures/CASE-09
./smoke.sh | tee case-09-smoke.log
```

From another host, export `PROOFIX_BASE_URL=http://K3S_NODE_IP:30079`.
Individual commands are `install.sh`, `inject.sh`, `verify.sh fault`, `reset.sh`,
`verify.sh recovered`, and `rollback-recovery.sh`.

Verification captures the pod identity, Role, RoleBinding, and impersonated
`can-i` decisions. Recovered service quality requires exactly three consecutive
windows, HTTP 5xx rate `< 0.001`, p95 `< 200ms`, and zero non-200 responses.
