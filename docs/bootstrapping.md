# Bootstrapping a cluster

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
[`templates/values.yaml.gotmpl`](../bootstrap/helmfile.d/templates/values.yaml.gotmpl)
reads each release's values straight out of its Flux `HelmRelease`
(`kubernetes/apps/<ns>/<app>/app/helmrelease.yaml`). Bootstrap and steady-state
therefore use **identical** configuration.

The one bootstrap secret (the `bitwarden-cli` ESO bridge login) is seeded
out-of-band from the private Omni repo — see [Secrets](secrets.md) and the
[cluster-rebuild runbook](runbooks/cluster-rebuild.md).

## Via Task

Every step is wrapped as a [Task](https://taskfile.dev) target — run `task`
to list them:

| Task | Does |
|------|------|
| `task cluster:kubeconfig` | Fetch the kubeconfig into `./kubeconfig` (from Omni) |
| `task bootstrap` | Install CRDs, then cluster prerequisites |
| `task reconcile` | Force a Flux sync from Git |

> Node provisioning (`omnictl cluster template …`) lives in the private Omni repo,
> not here — this repo picks up once the cluster's API is reachable.
