# Bootstrapping a cluster

Nodes come from Sidero Omni (private repo). Once `kubectl` reaches the API:

```sh
# 1. CRDs (external-dns, envoy-gateway, kube-prometheus-stack, grafana-operator)
helmfile --file bootstrap/helmfile.d/00-crds.yaml template \
  | yq ea 'select(.kind == "CustomResourceDefinition")' \
  | kubectl apply --server-side -f -

# 2. Prerequisites: cilium → coredns → cert-manager → flux-operator → flux-instance
helmfile --file bootstrap/helmfile.d/01-apps.yaml sync
```

`flux-instance` then clones this repo and Flux owns `kubernetes/apps/**`.

- **No duplicated values**: [`templates/values.yaml.gotmpl`](../bootstrap/helmfile.d/templates/values.yaml.gotmpl)
  reads each release's values from its Flux `HelmRelease`. Bootstrap = steady state.
- **One bootstrap secret** (`bitwarden-cli` ESO login) is seeded from the private Omni
  repo — [Secrets](secrets.md), [rebuild runbook](runbooks/cluster-rebuild.md).
- Helmfile applies with field manager `helm`, Flux with `helm-controller`. A value set at
  bootstrap and later removed in git stays in the live object until removed by hand.

## Task

| Task | Does |
|------|------|
| `task cluster:kubeconfig` | kubeconfig from Omni → `./kubeconfig` |
| `task bootstrap` | CRDs, then prerequisites |
| `task reconcile` | force Flux sync |
