# Operations & automation

## Automation

- **Renovate** ([`.renovaterc.json5`](../.renovaterc.json5)) — runs on weekends,
  pins GitHub Action digests, groups the Flux operator/instance releases, and
  writes [Conventional Commits](https://www.conventionalcommits.org/) with
  type/scope + `type/*` and `renovate/*` labels. Custom managers pick up
  `# renovate:`-annotated versions and any `oci://…:tag` reference.
- **GitHub Actions** ([`.github/workflows/`](../.github/workflows)) —
  `labeler` (PR labels by path) and `label-sync` (keeps repo labels in sync
  with [`.github/labels.yaml`](../.github/labels.yaml)).
- **Flux webhook** — a `Receiver`
  ([`flux-instance/app/receiver.yaml`](../kubernetes/apps/flux-system/flux-instance/app/receiver.yaml))
  reconciles immediately on `push` instead of waiting for the poll interval.

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
