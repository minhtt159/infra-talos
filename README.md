Get machines

```sh
omnictl get machine
```

Validate configuration file

```sh
omnictl cluster template validate -f temp-cluster/omni-cluster.yaml
```

Deploy cluster

```sh
omnictl cluster template sync -f temp-cluster/omni-cluster.yaml
```

Install CRDs

apps

- external-dns
- envoy-gateway
- kube-prometheus-stack

```sh
helmfile --file bootstrap/00-crds.yaml -b /opt/homebrew/opt/helm@3/bin/helm template > crds.yaml
kubectl apply --server-side -f crds.yaml
```

Install helm

apps

- cilium
- coredns

```sh
helmfile --file bootstrap/01-apps.yaml -b /opt/homebrew/opt/helm@3/bin/helm sync
```
