# CLAUDE.md

Guidance for AI assistants (and humans) working in this repo. Read this before making changes.

## What this repo is

Public GitOps for a home Kubernetes cluster on **Talos Linux** (provisioned by
**Sidero Omni**), reconciled by **Flux**. This repo owns **cluster prerequisites +
applications**: `bootstrap/helmfile.d/` (CNI/DNS/cert-manager/Flux seed) and
`kubernetes/` (everything Flux reconciles). Node/OS provisioning (the Omni cluster
template) lives in a **separate private repo** — a migration is in progress, so
**don't add new machine/topology detail here.**

## Security posture — hard rules

- **This repo is PUBLIC. No private information.** Never commit node/machine UUIDs,
  disk serials, LAN IPs, internal hostnames used as topology, hardware inventory, or
  anything mapping the physical setup. If you're about to write a real internal
  IP/serial/UUID, stop — it belongs in a private repo.
- **No plaintext secrets, ever.** Two mechanisms, both keep ciphertext or nothing in git:
  - **ExternalSecret** (preferred for new work) — pulls at runtime from Vaultwarden via
    `ClusterSecretStore/bitwarden-fields`; reference items by UUID + field, never inline the value.
  - **SOPS** (`*.sops.yaml`) — only `data`/`stringData`/`driver` are encrypted; the age
    **private key is not in the repo**. Being phased out in favor of ExternalSecret.
- Non-secret, cluster-wide values (`${SECRET_DOMAIN}`, …) come from the `cluster-secrets`
  Secret via `postBuild.substituteFrom` — don't hardcode them.
- **Before every commit:** no secrets, no private topology, and any `*.sops.yaml` is
  actually encrypted (`sops --encrypt`), not plaintext.

## Kyverno policies — write compliant manifests

Policies live in `kubernetes/apps/kyverno/kyverno/policies/policies.yaml`. They're in
**Audit** mode today (they report, don't block) but are meant to flip to Enforce — so
don't add to the violation backlog. New workloads must satisfy:

1. **Pinned image tags** — no `:latest`, no tagless image. A chart's `appVersion`
   default resolves to a pinned tag, which is fine.
2. **Resource requests** — every container sets `resources.requests.cpu` **and** `memory`.
3. **ServiceAccount token automount** — set `automountServiceAccountToken: false` unless
   the workload actually calls the Kubernetes API. Several infra namespaces are excluded;
   check the policy's exclude list rather than assuming yours is covered.

## Application pattern — match existing apps exactly

- One directory per app: `kubernetes/apps/<namespace>/<app>/`
  - `ks.yaml` — Flux `Kustomization`: `path:` → the app's `app/` dir, `targetNamespace`,
    `dependsOn` as needed, and `postBuild.substituteFrom: cluster-secrets` if manifests
    use `${…}` substitutions.
  - `app/` — an `OCIRepository` (the chart), a `HelmRelease` (`chartRef` → that
    OCIRepository), any `ExternalSecret`/extra CRs, and a `kustomization.yaml` listing them.
- Register the app's `ks.yaml` in the namespace's `kustomization.yaml`.
- **Charts are OCI artifacts** (`OCIRepository`, pinned by tag) — not classic
  `HelmRepository` (a few legacy exceptions remain).
- Copy an existing app (e.g. `kubernetes/apps/cert-manager/cert-manager/`) as the template.

## Dependencies — Renovate owns versions

- Everything is pinned and Renovate-tracked. **Don't hand-bump** versions — let Renovate
  open the PR.
- Annotate non-standard versions with `# renovate: datasource=… depName=…` on the line
  above the value. OCIRepository tags are picked up by the native `flux` manager; inline
  `oci://…:tag` by the OCI custom manager.

## Grafana dashboards

- Prefer the chart's **mixin** dashboards (they auto-update with the chart bump).
- If a chart ships none: a `GrafanaDashboard` with `grafanaCom` id **+ revision**, tracked
  by the `custom.grafana-dashboards` Renovate datasource (see `.renovaterc.json5`).
  **Don't** commit static, un-tracked grafana.com JSON — that goes stale.

## Conventions

- Conventional Commits (`type(scope): summary`).
- Match the surrounding style; keep diffs minimal.
- Full architecture, layers, and ops: see [README.md](README.md).
