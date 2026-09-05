# Runbook: node died or was reprovisioned

Node replaced on the Omni side (private repo), cluster back to full count. Finish the
Kubernetes side. See [Storage](../storage.md) for what is node-pinned.

## 1. Pods stuck on the dead node's volumes

Only `openebs-hostpath*` PVs are node-pinned; a pod on one stays `Pending`:

```sh
kubectl get pods -A --field-selector status.phase=Pending
kubectl get pv -o custom-columns='NS:.spec.claimRef.namespace,CLAIM:.spec.claimRef.name,SC:.spec.storageClassName,NODE:.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values[0]' | grep openebs
kubectl get nodes    # NODE missing here = dead volume
```

TrueNAS pods reschedule alone. An iSCSI (RWO) pod stuck in `ContainerCreating`
with "Multi-Attach": the dead node still holds the attachment.

```sh
kubectl get volumeattachment -o custom-columns='PV:.spec.source.persistentVolumeName,NODE:.spec.nodeName,ATTACHED:.status.attached'
kubectl delete volumeattachment <NODE no longer exists>
```

## 2. Kafka

Single broker, RF=1, accepts loss. PV = hostpath on the `storage=sata` node (label from
the Omni template). Strimzi can't move a PVC; give it a fresh one. Cluster ID lives in the
`Kafka` status, so the broker returns as the same cluster, empty.

```sh
kubectl get nodes -l storage=sata           # none → stays Pending until one exists
kubectl -n database delete pvc data-kafka-dual-0
kubectl -n database delete pod kafka-dual-0
kubectl -n database get pvc data-kafka-dual-0 -o jsonpath='{.metadata.annotations.volume\.kubernetes\.io/selected-node}'   # must be the sata node; else repeat
kubectl -n database get pods -w
kubectl get kafkatopics -A                  # recreated by the topic operator
```

`RegistrationResponseHandler` errors for ~2 min while KRaft bootstraps are normal.

## 3. Ollama (GPU node)

```sh
kubectl -n ai delete pvc ollama-models
kubectl -n ai delete pod -l app=ollama
kubectl -n ai exec deploy/ollama -- ollama pull qwen3:8b   # per model
```

## 4. Nothing else

Prometheus is an agent (loses minutes of WAL at most). Grafana, Postgres, Hindsight,
Frigate, Alertmanager are on TrueNAS. Operators and exporters are stateless.

## 5. Verify

```sh
flux get kustomizations -A
kubectl get pv | grep -v Bound   # nothing Released/Available
```

`Released` `openebs-hostpath*` PV with a gone node: `kubectl delete pv <name>`.
Never delete a `truenas-*` PV this way — `Retain` data is still there.
