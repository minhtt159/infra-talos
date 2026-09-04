# Storage

Two providers. Everything stateful sits on TrueNAS; one node-local class exists
for Kafka, which trades durability for local-disk latency on purpose.

```mermaid
flowchart LR
  subgraph truenas[TrueNAS via democratic-csi]
    iscsi[truenas-iscsi<br/>block, RWO, Retain]
    nfs[truenas-nfs<br/>shared, Retain]
  end
  subgraph node[one node's SATA SSD via openebs]
    sata[openebs-hostpath-sata<br/>pinned, Delete]
  end
  postgres & bank0 & ollama & hindsight & grafana --> iscsi
  frigate & alertmanager --> nfs
  kafka --> sata
  promagent[prometheus agent] -->|remote_write| promeo[(promeo: Prometheus on TrueNAS)]
```

- **democratic-csi** - dynamic PVs from a TrueNAS appliance over iSCSI (block)
  and NFS (shared). TrueNAS credentials come from Vaultwarden via an
  `ExternalSecret`; setup in [democratic-csi/README.md](../kubernetes/apps/democratic-csi/README.md).
  Both classes use `reclaimPolicy: Retain`, so deleting a PVC or the cluster
  never deletes data.
- **openebs** - node-local `hostpath` volumes. A PV here is pinned to the node
  that created it and dies with that node. Only Kafka uses it, through
  `openebs-hostpath-sata` (`/var/mnt/sata` on the node labelled
  `storage=sata`); the default `openebs-hostpath` class has no consumers.
- **Metrics** are not stored in-cluster. Prometheus runs in agent mode and
  remote-writes to `promeo`, a Prometheus on TrueNAS; Thanos Ruler evaluates
  the `PrometheusRule`s against it and alerts into the in-cluster Alertmanager.

## Which PVs survive what

| Event | TrueNAS PVs | Kafka PV |
|---|---|---|
| Pod restart | same data | same data |
| Node drain | reschedule, data intact | Pending until that node is back |
| Node loss / reprovision | reschedule, data intact | lost - [node loss runbook](runbooks/node-loss.md) |
| Cluster rebuild | reclaimed - [cluster rebuild runbook](runbooks/cluster-rebuild.md) | lost, recreated empty |
| TrueNAS disk loss | lost (no VolSync yet) | intact |

To list what is where:

```sh
kubectl get pv -o custom-columns='CLAIM:.spec.claimRef.namespace,NAME:.spec.claimRef.name,SC:.spec.storageClassName,NODE:.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]'
```
