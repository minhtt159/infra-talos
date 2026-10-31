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
   for the `${SECRET_*}` values.
4. **`app/`** — `OCIRepository` (chart, pinned tag), `HelmRelease` (`chartRef`),
   `ExternalSecret`, extra CRs (ClusterIssuer, HTTPRoute, …), `kustomization.yaml`.

Charts are OCI artifacts, not classic Helm repositories.

## Applications

One row per namespace under [`kubernetes/apps/`](../kubernetes/apps); each app is a subdirectory.

| Namespace | Apps | Purpose |
|-----------|------|---------|
| `ai` | hindsight, litellm, llama-server, yoke | agent memory, OpenAI-compatible LLM proxy, LLM serving on the B580, Claude Code session hub |
| `argocd` | argo-rollouts, argocd | app delivery (reads `kubernetes/argocd/`, not Flux), progressive rollouts |
| `bank0-production` | bank0 | bank0 platform half: Postgres, routes, Access JWT, rate limits (workload via Argo CD) |
| `bank0-staging` | bank0 | same, staging |
| `cert-manager` | cert-manager | Let's Encrypt + internal CA |
| `database` | barman-cloud-plugin, cloudnative-pg, kafka, postgres, strimzi-operator, valkey | CNPG operator + S3 backups, shared Postgres, single-broker Kafka, cache |
| `default` | (none) | namespace only |
| `democratic-csi` | iscsi, nfs | TrueNAS-backed PVs |
| `external-secrets` | external-secrets | ESO + bitwarden-cli bridge to Vaultwarden |
| `flux-system` | flux-instance, flux-operator | Flux |
| `frigate` | frigate | NVR, detection on the Coral TPU; raw manifests |
| `functions` | hello | Knative smoke function / cold-start canary |
| `headlamp` | headlamp | Kubernetes UI (mainly Knative), LAN-only |
| `home` | mosquitto | MQTT broker on a LAN LoadBalancer |
| `kargo` | bank0, kargo | promotion pipeline (bank0 staging → production) |
| `knative-serving` | knative-operator, knative-serving | serverless functions (Serving only) |
| `kube-system` | cilium, coredns, drm-exporter, intel-device-plugin, kubelet-csr-approver, metrics-server, node-feature-discovery, rbac, reloader, snapshot-controller, spegel | CNI + BGP LB, DNS, GPU discovery/metrics, cluster RBAC, image mirror, core controllers |
| `kyverno` | kyverno | admission policies |
| `network` | cloudflare-dns, cloudflare-tunnel, envoy-gateway, unifi-dns, valkey | Gateway API edge, external-dns (Cloudflare + UniFi), tunnel, rate-limit store |
| `observability` | elasticsearch-exporter, es-policies, fluent-bit, gatus, grafana, kibana, kube-prometheus-stack, smartctl-exporter | metrics (agent → promeo), logs → TrueNAS ES, Grafana, uptime probes |
| `openebs` | openebs | node-local hostpath (Kafka, llama-server models, mosquitto) |
| `research` | browserless, searxng | headless Chrome, metasearch |

## Adding an app

1. `kubernetes/apps/<namespace>/<app>/app/`: OCIRepository, HelmRelease, ExternalSecret
   (Vaultwarden item UUID + field, never the value), `kustomization.yaml`.
2. `ks.yaml` → `app/`, with `healthChecks` and `postBuild.substituteFrom` as needed.
3. Register `ks.yaml` in the namespace `kustomization.yaml` (new namespace: add
   `namespace.yaml` + its `kustomization.yaml`).
4. Push; the Flux `Receiver` reconciles. Copy `cert-manager` as the template.

Kyverno rules (pinned tags, requests, SA-token automount): [CLAUDE.md](../CLAUDE.md).
