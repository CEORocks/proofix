# CASE-01 — VirtualService subset mismatch

This fixture installs two real sidecar-injected checkout pods, an Istio
`DestinationRule` defining only `v1`, an ingress `VirtualService`, and a
non-meshed diagnostic pod used only for direct-pod evidence. The fixed
NodePort is `30081` on the benchmark node.

`install.sh` creates a healthy `v1` route. `inject.sh` deterministically changes
the route to undefined subset `v2` and does not return until ingress produces
HTTP 503. `reset.sh` restores the preregistered safe recovery. The recovery's
rollback is the fault patch.

Run on a cluster with Istio 1.30.4 installed and `KUBECONFIG` configured:

```bash
./install.sh
./inject.sh
./verify-evidence.sh
./reset.sh
```
