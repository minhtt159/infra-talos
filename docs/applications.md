# Application pattern

Chain, using `cert-manager` as the example:

1. **Root** — [`kubernetes/flux/cluster/ks.yaml`](../kubernetes/flux/cluster/ks.yaml):
   Kustomization `cluster-apps` → `./kubernetes/apps`. Patches every HelmRelease
   with install/upgrade/rollback remediation and `CreateReplace` CRDs.
2. **Namespace** — [`kubernetes/apps/cert-manager/kustomization.yaml`](../kubernetes/apps/cert-manager/kustomization.yaml):
   `namespace.yaml` + each app's `ks.yaml`. `cluster-secrets` is fanned out to every
   namespace by a ClusterExternalSecret (`external-secrets/.../stores/`).
3. **App `ks.yaml`** — [`cert-manager/cert-manager/ks.yaml`](../kubernetes/apps/cert-manager/cert-manager/ks.yaml):
   Flux Kustomization → `app/`; `healthChecks`; `postBuild.substituteFrom: cluster-secrets`
   for `${SECRET_DOMAIN}` and friends.
4. **`app/`** — `OCIRepository` (chart, pinned tag), `HelmRelease` (`chartRef`),
   `ExternalSecret`, extra CRs (ClusterIssuer, HTTPRoute, …), `kustomization.yaml`.

Charts are OCI artifacts, not classic Helm repositories.

## Applications

| Namespace | Apps | Purpose |
|-----------|------|---------|
| `kube-system` | cilium, coredns, metrics-server, reloader, node-feature-discovery, intel-device-plugin | CNI + BGP LB, DNS, HPA metrics, config-change restarts, GPU discovery (`gpu.intel.com/xe`) |
| `cert-manager` | cert-manager | Let's Encrypt + internal CA |
| `external-secrets` | external-secrets | ESO + bitwarden-cli bridge to Vaultwarden |
| `kyverno` | kyverno | Policies, all Audit |
| `network` | envoy-gateway, cloudflare-dns, unifi-dns, cloudflare-tunnel | Gateway API edge, external-dns (Cloudflare + UniFi), tunnel |
| `observability` | kube-prometheus-stack, grafana, elasticsearch-exporter | Prometheus agent → promeo (TrueNAS), Thanos Ruler + Alertmanager, Grafana (operator), external ES |
| `democratic-csi` | iscsi, nfs | TrueNAS-backed PVs |
| `openebs` | openebs | Node-local hostpath (Kafka, Ollama cache) |
| `database` | postgres, strimzi-operator, kafka, valkey | CloudNativePG on iSCSI, single-broker Kafka on SATA, cache |
| `frigate` | frigate | NVR on the Intel dGPU (OpenVINO); raw manifests |
| `ai` | ollama, litellm, hindsight | LLM serving (IPEX), OpenAI-compatible proxy, agent memory |
| `flux-system` | flux-operator, flux-instance | Flux + dashboards |
| `default` | echo | smoke test |

## Adding an app

1. `kubernetes/apps/<namespace>/<app>/app/`: OCIRepository, HelmRelease, ExternalSecret
   (Vaultwarden item UUID + field, never the value), `kustomization.yaml`.
2. `ks.yaml` → `app/`, with `healthChecks` and `postBuild.substituteFrom` as needed.
3. Register `ks.yaml` in the namespace `kustomization.yaml` (new namespace: add
   `namespace.yaml` + its `kustomization.yaml`).
4. Push; the Flux `Receiver` reconciles. Copy `cert-manager` as the template.

Kyverno rules (pinned tags, requests, SA-token automount): [CLAUDE.md](../CLAUDE.md).
