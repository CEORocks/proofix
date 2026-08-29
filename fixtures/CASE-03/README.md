# CASE-03 — Service targetPort mismatch

This single-node-k3s fixture exposes `catalog-api` on fixed NodePort `30073`.
The digest-pinned nginx pods really listen on `8081`; injection changes only
the Service `targetPort` to `8080`. EndpointSlices still contain ready pod
addresses, direct pod probes still pass on `8081`, and Service traffic fails.

Run `./smoke.sh` on the k3s node, or set
`PROOFIX_BASE_URL=http://K3S_NODE_IP:30073` first. The accepted recovery is the
small, reversible Service patch to named port `catalog-http` (container port
`8081`); `rollback-recovery.sh` deliberately restores the incident.

`verify.sh recovered` requires three consecutive windows with HTTP 5xx rate
`< 0.001`, p95 latency `< 200ms`, and no non-200 responses.
