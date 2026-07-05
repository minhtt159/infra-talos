# infra-talos

GitOps configuration for a home Kubernetes cluster running on **Talos Linux**,
provisioned by **Sidero Omni** and continuously reconciled by **Flux**.
Secrets are pulled from **Vaultwarden** via the **External Secrets Operator**;
dependency updates are automated with **Renovate**.

The layout follows the [onedr0p / home-operations](https://github.com/onedr0p/cluster-template)
convention: every application is a self-contained Flux `Kustomization` that
points at an `app/` directory holding a `HelmRelease` (or raw manifests).

---

## Table of contents

- [Architecture](#architecture)
- [Cluster shape](#cluster-shape)
- [Repository layout](#repository-layout)
- [The application pattern](#the-application-pattern)
- [Applications](#applications)
- [Networking & ingress](#networking--ingress)
- [Storage](#storage)
- [Secrets (External Secrets Operator)](#secrets-external-secrets-operator)
- [Bootstrapping a cluster](#bootstrapping-a-cluster)
- [Automation](#automation)
- [Common operations](#common-operations)
- [Adding a new application](#adding-a-new-application)

---

## Architecture

Three layers, each owned by a different tool:

| Layer | Tool | Source of truth |
|-------|------|-----------------|
| **1. Machine / OS** | Sidero Omni + Talos | Omni cluster template — in a **separate private repo** (node UUIDs, disk serials, LAN topology are not published here) |
| **2. Cluster prerequisites** | Helmfile | [`bootstrap/helmfile.d/`](bootstrap/helmfile.d) — CNI, DNS, cert-manager, Flux itself |
| **3. Applications** | Flux (GitOps) | [`kubernetes/`](kubernetes) |

This repo owns layers **2 & 3** (public GitOps). Layer 1 — node provisioning via
Sidero Omni — lives in a private repo alongside the Omni management plane.

Once layer 3 is up, **Flux owns everything** — including the components that
were seeded by Helmfile in layer 2. The Helmfile step exists only to break the
chicken-and-egg problem of installing Flux (and the CNI it needs) before Flux
exists to install them.

```mermaid
flowchart TD
    Omni[Sidero Omni<br/>provisions Talos nodes] --> HF[Helmfile bootstrap<br/>cilium, coredns, cert-manager, flux]
    HF --> FI[flux-instance<br/>syncs this Git repo]
    FI --> ROOT[kubernetes/flux/cluster/ks.yaml<br/>Kustomization: cluster-apps]
    ROOT --> APPS[kubernetes/apps/**<br/>per-namespace Kustomizations]
    APPS --> HR[HelmReleases + raw manifests]
```

---

## Cluster shape

Provisioned by Sidero Omni. The node inventory, hardware, disk pinning, and Talos
machine config live in a **separate private repo** — not published here. What the
GitOps layer in this repo relies on:

- **Mixed architecture** (amd64 + arm64) — charts/images must be multi-arch;
  arch-picky workloads pin `kubernetes.io/arch` via nodeSelector.
- **CNI `none` + kube-proxy disabled** at the Talos layer — Cilium replaces both
  (`kube-system/cilium`).
- **CoreDNS disabled** at the Talos layer — deployed as an app instead
  (`kube-system/coredns`).
- Control planes are schedulable, so master/worker is logical, not a hard boundary.
- A **Coral TPU** (`capability=coral`) and an **Intel Arc B580** (`gpu.intel.com/xe`)
  are exposed to the workloads that select them (frigate, ollama).

---

## Repository layout

```
.
├── bootstrap/                     # Layer 2 — cluster prerequisites (Flux not up yet)
│   └── helmfile.d/
│       ├── 00-crds.yaml            # CRDs only (external-dns, envoy-gateway, grafana, kps)
│       ├── 01-apps.yaml            # cilium → coredns → cert-manager → flux-operator → flux-instance
│       └── templates/values.yaml.gotmpl   # reuses each app's HelmRelease values (see below)
│
├── kubernetes/                    # Layer 3 — everything Flux reconciles
│   ├── flux/cluster/ks.yaml        # ROOT Kustomization "cluster-apps" → ./kubernetes/apps
│   └── apps/<namespace>/           # one directory per namespace
│       ├── namespace.yaml
│       ├── kustomization.yaml       # lists the namespace's apps
│       └── <app>/
│           ├── ks.yaml              # Flux Kustomization for this app
│           └── app/                 # HelmRelease, OCIRepository, secrets, extra manifests
│
├── Taskfile.yaml                  # task runner — Omni cred fetch, helmfile bootstrap, Flux/PV ops
├── .renovaterc.json5              # Renovate config
└── .envrc                         # direnv: exports KUBECONFIG
```

---

## The application pattern

Every app is reconciled through the same chain. Using `cert-manager` as the
example:

1. **Root Kustomization** — [`kubernetes/flux/cluster/ks.yaml`](kubernetes/flux/cluster/ks.yaml)
   defines `cluster-apps`, pointing at `./kubernetes/apps`. It applies **global
   defaults to every child** via `patches`: a `HelmRelease` patch that sets
   install/upgrade/rollback remediation (retry, `cleanupOnFail`, `CreateReplace` CRDs).

2. **Namespace Kustomization** — [`kubernetes/apps/cert-manager/kustomization.yaml`](kubernetes/apps/cert-manager/kustomization.yaml)
   lists `namespace.yaml` and each app's `ks.yaml`, and pulls in the
   `cluster-secrets` Secret (fanned out to every namespace by the ClusterExternalSecret in `kubernetes/apps/external-secrets/.../stores/`).

3. **App Kustomization (`ks.yaml`)** — [`kubernetes/apps/cert-manager/cert-manager/ks.yaml`](kubernetes/apps/cert-manager/cert-manager/ks.yaml)
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
| `observability` | kube-prometheus-stack, grafana | Metrics/alerting stack, Grafana (via grafana-operator) |
| `democratic-csi` | iscsi, nfs | TrueNAS-backed persistent storage (iSCSI + NFS) |
| `openebs` | openebs | Local-path persistent volumes |
| `frigate` | frigate | NVR — detection on the Intel dGPU (OpenVINO); raw manifests (not Helm) |
| `ai` | ollama | LLM serving on the Intel dGPU (IPEX build) |
| `flux-system` | flux-operator, flux-instance | Flux itself + monitoring dashboards |
| `default` | echo | Ingress/connectivity smoke test |

---

## Networking & ingress

- **LoadBalancer IPs** — Cilium LB IPAM, pool `10.1.80.0/24`, announced over
  L2 on `ens*`/`eth*` interfaces
  ([`cilium/app/networks.yaml`](kubernetes/apps/kube-system/cilium/app/networks.yaml)).
- **Gateways** (Envoy Gateway, Gateway API) —
  [`envoy-gateway/gateway/`](kubernetes/apps/network/envoy-gateway/gateway):
  - `envoy-internal` → `10.1.80.11`, host `internal.${SECRET_DOMAIN}`
  - `envoy-external` → `10.1.80.12`, host `external.${SECRET_DOMAIN}`
  - both terminate TLS with the `${SECRET_DOMAIN}-production-tls` wildcard cert.
    Apps attach via `HTTPRoute` (see each app's `httproute.yaml`).
- **DNS** — `external-dns` publishes gateway hostnames to **Cloudflare**
  (`cloudflare-dns`) and **UniFi** (`unifi-dns`).
- **External access** — `cloudflare-tunnel` (cloudflared) exposes selected
  services without opening ports.
- **Certificates** — cert-manager `letsencrypt-production` ClusterIssuer
  (DNS-01 over 1.1.1.1) plus an `internal-ca` issuer.

---

## Storage

- **openebs** — node-local volumes for scratch / non-replicated data.
- **democratic-csi** — dynamic PVs backed by a **TrueNAS** appliance over
  **iSCSI** (block) and **NFS** (shared). TrueNAS credentials come from Vaultwarden
  via an `ExternalSecret`. See [`democratic-csi/README.md`](kubernetes/apps/democratic-csi/README.md).
- **Rebuild survival** — both TrueNAS storage classes use
  `reclaimPolicy: Retain`; volumes are reclaimed after a full cluster
  recreation via `task pv:export` + the
  [cluster-rebuild runbook](docs/runbooks/cluster-rebuild.md).

---

## Secrets (External Secrets Operator)

Secrets are pulled at runtime from **Vaultwarden** by the **External Secrets
Operator** (ESO) — nothing secret is committed to this repo (no SOPS, no age key).

- Each app declares an `ExternalSecret` (`secretStoreRef` →
  `ClusterSecretStore/bitwarden-fields`) mapping a Vaultwarden item's fields into a
  Kubernetes `Secret`.
- Non-secret, cluster-wide values (e.g. `${SECRET_DOMAIN}`) live in the
  `cluster-secrets` Vaultwarden item, fanned out to every namespace by a
  `ClusterExternalSecret` and injected via `postBuild.substituteFrom`.
- ESO reaches Vaultwarden through an in-cluster `bitwarden-cli` bridge. Its login
  is the one **bootstrap** secret that can't come from ESO itself — seeded
  out-of-band (SOPS-encrypted in the **private** Omni repo, applied by a seed task;
  see the [rebuild runbook](docs/runbooks/cluster-rebuild.md)) and **not** stored here.

> If a workload needs a secret, add an `ExternalSecret` — never commit the value
> (encrypted or not).

---

## Bootstrapping a cluster

Nodes are provisioned by **Sidero Omni** from a separate private repo. Once they
are up and `kubectl` reaches the API, seed the cluster prerequisites:

```sh
# 1. Install CRDs (external-dns, envoy-gateway, kube-prometheus-stack, grafana-operator)
helmfile --file bootstrap/helmfile.d/00-crds.yaml template \
  | yq ea 'select(.kind == "CustomResourceDefinition")' \
  | kubectl apply --server-side -f -

# 2. Install cluster prerequisites (cilium → coredns → cert-manager → flux-operator → flux-instance)
helmfile --file bootstrap/helmfile.d/01-apps.yaml sync
```

After step 2, `flux-instance` clones this repo and Flux reconciles
`kubernetes/apps/**` on its own.

**Why the Helmfile values are never duplicated:**
[`templates/values.yaml.gotmpl`](bootstrap/helmfile.d/templates/values.yaml.gotmpl)
reads each release's values straight out of its Flux `HelmRelease`
(`kubernetes/apps/<ns>/<app>/app/helmrelease.yaml`). Bootstrap and steady-state
therefore use **identical** configuration.

### Via Task

Every step is wrapped as a [Task](https://taskfile.dev) target — run `task`
to list them:

| Task | Does |
|------|------|
| `task cluster:kubeconfig` | Fetch the kubeconfig into `./kubeconfig` (from Omni) |
| `task bootstrap` | Install CRDs, then cluster prerequisites |
| `task reconcile` | Force a Flux sync from Git |

> Node provisioning (`omnictl cluster template …`) lives in the private Omni repo,
> not here — this repo picks up once the cluster's API is reachable.

---

## Automation

- **Renovate** ([`.renovaterc.json5`](.renovaterc.json5)) — runs on weekends,
  pins GitHub Action digests, groups the Flux operator/instance releases, and
  writes [Conventional Commits](https://www.conventionalcommits.org/) with
  type/scope + `type/*` and `renovate/*` labels. Custom managers pick up
  `# renovate:`-annotated versions and any `oci://…:tag` reference.
- **GitHub Actions** ([`.github/workflows/`](.github/workflows)) —
  `labeler` (PR labels by path) and `label-sync` (keeps repo labels in sync
  with [`.github/labels.yaml`](.github/labels.yaml)).
- **Flux webhook** — a `Receiver`
  ([`flux-instance/app/receiver.yaml`](kubernetes/apps/flux-system/flux-instance/app/receiver.yaml))
  reconciles immediately on `push` instead of waiting for the poll interval.

---

## Common operations

Requires `kubectl` + `flux` against the cluster (`.envrc` sets `KUBECONFIG`).

```sh
# Force-reconcile the whole tree from Git
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization cluster-apps -n flux-system --with-source

# Reconcile / suspend / resume a single app
flux reconcile kustomization <app> -n flux-system
flux suspend   kustomization <app> -n flux-system
flux resume    kustomization <app> -n flux-system

# See what's failing
flux get kustomizations -A
flux get helmreleases -A

# Change a secret: edit the item in Vaultwarden, then force ESO to re-sync
flux reconcile kustomization <app> -n flux-system   # or wait for the refreshInterval
```

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
```
