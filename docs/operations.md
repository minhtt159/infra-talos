# Operations & automation

- **Renovate** ([`.renovaterc.json5`](../.renovaterc.json5)) — weekends; pins Action
  digests; groups Flux operator/instance; Conventional Commits + `type/*`, `renovate/*`
  labels. Custom managers: `# renovate:` annotations and `oci://…:tag`.
- **GitHub Actions** ([`.github/workflows/`](../.github/workflows)) — `labeler`,
  `label-sync` ([`.github/labels.yaml`](../.github/labels.yaml)), PR title/size checks.
- **Flux webhook** — [`receiver.yaml`](../kubernetes/apps/flux-system/flux-instance/app/receiver.yaml)
  reconciles on push.

## Day 2

`kubectl` + `flux` against the cluster (`.envrc` sets `KUBECONFIG`).

```sh
flux reconcile source git flux-system -n flux-system
flux reconcile kustomization cluster-apps -n flux-system --with-source

flux reconcile kustomization <app> -n <ns>
flux suspend   kustomization <app> -n <ns>
flux resume    kustomization <app> -n <ns>

flux get kustomizations -A
flux get helmreleases -A

# secret change: edit in Vaultwarden, then reconcile the app (or wait for refreshInterval)
```
