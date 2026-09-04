# Runbook: a node died or was reprovisioned

You replaced or lost a node (Omni side, private repo) and the cluster is back
to full node count. This runbook finishes the Kubernetes side.

Prerequisites: [Storage](../storage.md) for which PVs are node-pinned; Flux and
Strimzi basics.

## 1. Find pods stuck on the dead node's volumes

Only `openebs-hostpath*` PVs are node-pinned. A pod whose PV points at a node
that no longer exists stays `Pending` forever:

```sh
kubectl get pods -A --field-selector status.phase=Pending
kubectl get pv -o custom-columns='NS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name,SC:.spec.storageClassName,NODE:.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]' | grep openebs
kubectl get nodes   # NODE above missing here = dead volume
```

TrueNAS-backed pods (`truenas-iscsi`, `truenas-nfs`) reschedule on their own.
An iSCSI (RWO) pod can stay `ContainerCreating` with a "Multi-Attach" event
while the dead node still holds the attachment:

```sh
kubectl get volumeattachment -o custom-columns='PV:.spec.source.persistentVolumeName,NODE:.spec.nodeName,ATTACHED:.status.attached'
kubectl delete volumeattachment <one whose NODE no longer exists>
```

## 2. Recover Kafka

Kafka accepts data loss on node loss (single broker, RF=1, transient topics).
Its PV is a hostpath on the node labelled `storage=sata`; the label comes from
the Omni cluster template (private repo). If no node carries it, Kafka stays
`Pending` after this step until one does:

```sh
kubectl get nodes -l storage=sata
```

Strimzi cannot move a PVC, so give it a fresh one. The claim outlives the
`Kafka` CR (`deleteClaim: false`), so delete it by hand; the cluster ID lives
in the `Kafka` status, not on disk, so the broker comes back as the same
cluster, empty:

```sh
kubectl -n database delete pvc data-kafka-dual-0
kubectl -n database delete pod kafka-dual-0
kubectl -n database get pvc data-kafka-dual-0 -o jsonpath='{.metadata.annotations.volume\.kubernetes\.io/selected-node}'
kubectl -n database get pods -w
kubectl get kafkatopics -A          # declarative topics, recreated by the topic operator
```

The `selected-node` must be the `storage=sata` node. If Strimzi recreated the
pod before rolling out the node affinity, the provisioner pins the new PV to
whatever node the old pod was on; delete the PVC and pod once more. The broker
logs `RegistrationResponseHandler` errors for the first ~2 minutes while the
fresh KRaft metadata log bootstraps; it goes `1/1` on its own.

## 3. Recover Ollama (GPU node only)

Models are a cache on the GPU node's local disk. Same shape as Kafka: fresh
claim, then the models come back on first use (or pull them now):

```sh
kubectl -n ai delete pvc ollama-models
kubectl -n ai delete pod -l app=ollama
kubectl -n ai exec deploy/ollama -- ollama pull qwen3:8b   # repeat per model you want warm
```

## 4. Nothing else needs you

- **Prometheus** is an agent: no storage, the new pod resumes remote-writing
  to promeo. At most the in-flight WAL (minutes) is lost.
- **Grafana, Postgres, Hindsight, Frigate, Alertmanager** are on TrueNAS.
- **Prometheus operator, Thanos Ruler, exporters** are stateless.

## 5. Verify

```sh
flux get kustomizations -A     # all Ready
kubectl get pv | grep -v Bound # nothing Released, nothing Available
```

A `Released` `openebs-hostpath*` PV whose node is gone is garbage:
`kubectl delete pv <name>`. Never delete a `truenas-*` PV this way - `Retain`
means the data is still there and the cluster rebuild runbook reclaims it.
