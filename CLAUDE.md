# CLAUDE.md

Guidance for AI assistants (and humans) working in this repo. Read this before making changes.

## What this repo is

Public GitOps for a home **Talos** cluster: **Flux** reconciles `kubernetes/flux/cluster` + `kubernetes/apps`; **Argo CD** reads `kubernetes/argocd/` (see its README).
Node/OS provisioning (the Omni cluster template) lives in a **separate private repo**. Architecture and ops: [README.md](README.md).

## Security posture — hard rules

- **This repo is PUBLIC. No private information.** Functional network values the manifests need — CIDRs, LoadBalancer VIPs, the router IP — are fine; never node IPs, node hostnames, disk serials, machine UUIDs, or hardware inventory. If you're about to write one of those, stop — it belongs in a private repo.
- The domain `hnimn.art` is public — write it literally.
- **No secrets in git, ever.** Secrets come from **Vaultwarden** via an `ExternalSecret` (item UUID + field, never the value); no SOPS, no age key. How-to: [docs/secrets.md](docs/secrets.md).
- `postBuild.substituteFrom: cluster-secrets` is only for the remaining `SECRET_*` keys (Cloudflare Access team, Access AUD tags, TrueNAS IP).

## Kyverno policies — write compliant manifests

`kubernetes/apps/kyverno/kyverno/policies/policies.yaml`: three validate policies plus the litellm cosign verify, all **Enforce** (non-compliant pods are rejected). New workloads need:

1. **Pinned image tags** — no `:latest`, no tagless image (a chart's `appVersion` default is fine).
2. **Resource requests** — every container sets `resources.requests.cpu` **and** `memory`.
3. **`automountServiceAccountToken: false`** unless the workload calls the Kubernetes API. Exclusions live in the policy file — check it, don't assume.

## Application pattern — match existing apps exactly

- Copy `kubernetes/apps/cert-manager/cert-manager/`: `ks.yaml` + `app/` (`OCIRepository` pinned by tag, `HelmRelease` with `chartRef`, extra CRs, `kustomization.yaml`); register `ks.yaml` in the namespace's `kustomization.yaml`.
- Classic `HelmRepository` only when the chart has no OCI artifact (today: headlamp, intel-device-plugin, knative-operator).
- `ks.yaml` carries only `path`, `targetNamespace`, `dependsOn`, `healthChecks`, `postBuild`; `sourceRef`/`prune`/`interval` are defaulted by the `cluster-apps` patch.

## Dependencies — Renovate owns versions

- Everything is pinned and Renovate-tracked. **Don't hand-bump.** Non-standard versions get `# renovate: datasource=… depName=…` on the line above.
- Dashboard-approval gates (no automatic PR) hold llama.cpp, kibana and bitwarden-cli — `.renovaterc.json5` says why.

## Grafana dashboards

- Chart **mixin** first; else a `GrafanaDashboard` with `grafanaCom` id **+ revision**, or a pinned upstream `url:`. Repo-owned JSON only when no upstream dashboard exists.
- Always `spec.folderUID` (folders in `kubernetes/apps/observability/grafana/instance/grafanafolder.yaml`); **never** `spec.folder` — it adopts folders by title and lands in the wrong one. Chart-rendered dashboards that only offer a title get `folderUID` through a `postRenderers` patch (see drm-exporter).

## Working here

- Worktrees lack `./kubeconfig` (gitignored) — use the main checkout's. Read-only cluster checks are fine.
- Design rationale and incident history go to the private homelab-platform repo; manifest comments stay "what + gotcha", ≤3 lines.
- Conventional Commits (`type(scope): summary`); match the surrounding style, keep diffs minimal. **Before every commit:** no secrets, no private topology.
