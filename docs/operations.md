# Operations & automation

- **Renovate** ([`.renovaterc.json5`](../.renovaterc.json5)) — weekends; pins Action
  digests; groups Flux operator/instance; Conventional Commits. Custom managers:
  `# renovate:` annotations, CNPG `imageName:` and `oci://…:tag`.
- **GitHub Actions** ([`.github/workflows/`](../.github/workflows)) — PR title check
  (Conventional Commits).
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
