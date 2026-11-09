# Storage

State on TrueNAS. Node-local disk only where speed beats durability: Kafka (accepts
loss), the llama-server model cache (re-pulled from Hugging Face) and mosquitto
(retained messages only). iSCSI ≈ 1GbE, ~125 MB/s.

![Storage: apps → TrueNAS iSCSI/NFS or node-local openebs; prometheus agent remote-writes to promeo](storage.svg)

- **truenas-csi** — official TrueNAS driver: iSCSI (block) + NFS (shared),
  `truenas-csi-{iscsi,nfs}` classes; creds via `ExternalSecret` from Vaultwarden;
  [kubernetes/apps/truenas-csi/](../kubernetes/apps/truenas-csi/).
  `reclaimPolicy: Retain`: deleting a PVC or the cluster never deletes data.
  TrueNAS-side steps and the democratic-csi migration history: homelab-platform (private).
- **openebs** — hostpath, pinned to the creating node, dies with it. Kafka on
  `openebs-hostpath-sata` (`/var/mnt/sata`, node `storage=sata`); llama-server models
  (GPU node) and mosquitto on `openebs-hostpath` (`/var/mnt/data` = Talos EPHEMERAL partition).
- **Metrics** not stored in-cluster: Prometheus agent remote-writes to `promeo`; Thanos
  Ruler evaluates rules there, alerts into in-cluster Alertmanager.

## What survives what

| Event | TrueNAS PVs | Node-local PVs |
|---|---|---|
| Pod restart | same data | same data |
| Node drain | reschedule | Pending until node returns |
| Node loss / reprovision | reschedule | lost, recreated empty — [node loss](runbooks/node-loss.md) |
| Cluster rebuild | reclaimed — [cluster rebuild](runbooks/cluster-rebuild.md) | lost |
| TrueNAS disk loss | lost (no VolSync yet) | intact |

```sh
kubectl get pv -o custom-columns='CLAIM:.spec.claimRef.namespace,NAME:.spec.claimRef.name,SC:.spec.storageClassName,NODE:.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]'
```
