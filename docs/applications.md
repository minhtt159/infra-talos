# Application pattern

Every app is reconciled through the same chain. Using `cert-manager` as the
example:

1. **Root Kustomization** — [`kubernetes/flux/cluster/ks.yaml`](../kubernetes/flux/cluster/ks.yaml)
   defines `cluster-apps`, pointing at `./kubernetes/apps`. It applies **global
   defaults to every child** via `patches`: a `HelmRelease` patch that sets
   install/upgrade/rollback remediation (retry, `cleanupOnFail`, `CreateReplace` CRDs).

2. **Namespace Kustomization** — [`kubernetes/apps/cert-manager/kustomization.yaml`](../kubernetes/apps/cert-manager/kustomization.yaml)
   lists `namespace.yaml` and each app's `ks.yaml`, and pulls in the
   `cluster-secrets` Secret (fanned out to every namespace by the ClusterExternalSecret in `kubernetes/apps/external-secrets/.../stores/`).

3. **App Kustomization (`ks.yaml`)** — [`kubernetes/apps/cert-manager/cert-manager/ks.yaml`](../kubernetes/apps/cert-manager/cert-manager/ks.yaml)
   is a Flux `Kustomization` that:
   - points `path` at the app's `app/` directory,
   - declares `healthChecks` (Flux waits for the HelmRelease + ClusterIssuer),
   - runs `postBuild.substituteFrom` against the `cluster-secrets` Secret, so
     manifests can reference `${SECRET_DOMAIN}` and friends.

4. **The `app/` directory** holds the actual resources: an `OCIRepository`
   (the Helm chart, pinned by tag), a `HelmRelease` referencing it, an
   `ExternalSecret` for any secrets, and any extra CRs (ClusterIssuer, HTTPRoute, …).

Charts are pulled as **OCI artifacts** (`OCIRepository`) rather than classic
Helm repositories.

---

## Applications

| Namespace | Apps | Purpose |
|-----------|------|---------|
| `kube-system` | cilium, coredns, metrics-server, reloader, node-feature-discovery, intel-device-plugin | CNI + LB, cluster DNS, HPA metrics, config-change restarts, GPU discovery + `gpu.intel.com/xe` scheduling |
| `cert-manager` | cert-manager | ACME (Let's Encrypt) + internal CA |
| `external-secrets` | external-secrets | ESO + bitwarden-cli bridge to Vaultwarden |
| `kyverno` | kyverno | Policy engine — all ClusterPolicies in Audit mode (PolicyReports), enforce per-policy later |
| `network` | envoy-gateway, cloudflare-dns, unifi-dns, cloudflare-tunnel | Gateway API ingress, external-dns (Cloudflare + UniFi), Cloudflare tunnel |
| `observability` | kube-prometheus-stack, grafana, elasticsearch-exporter | Metrics/alerting stack, Grafana (via grafana-operator), external ES monitoring |
| `democratic-csi` | iscsi, nfs | TrueNAS-backed persistent storage (iSCSI + NFS) |
| `openebs` | openebs | Local-path persistent volumes |
| `frigate` | frigate | NVR — detection on the Intel dGPU (OpenVINO); raw manifests (not Helm) |
| `ai` | ollama | LLM serving on the Intel dGPU (IPEX build) |
| `flux-system` | flux-operator, flux-instance | Flux itself + monitoring dashboards |
| `default` | echo | Ingress/connectivity smoke test |

---

## Adding a new application

1. Create `kubernetes/apps/<namespace>/<app>/` with an `app/` subdirectory.
2. In `app/`, add an `OCIRepository` (chart), a `HelmRelease` referencing it,
   an `app/kustomization.yaml` listing the files, and any secrets as an
   `ExternalSecret` (store the value in Vaultwarden, ref it by item UUID + field).
3. Add `ks.yaml` (Flux `Kustomization`) pointing `path` at the `app/` dir; add
   `healthChecks` and `postBuild.substituteFrom: cluster-secrets` as needed.
4. Reference the new `ks.yaml` from the namespace's `kustomization.yaml`
   (create `namespace.yaml` + the namespace `kustomization.yaml` if the
   namespace is new).
5. Commit and push — the Flux `Receiver` triggers reconciliation. Copy an
   existing app (e.g. `cert-manager`) as a template.

New workloads must satisfy the Kyverno policies (pinned image tags, resource
requests, ServiceAccount-token automount) — see [CLAUDE.md](../CLAUDE.md).
