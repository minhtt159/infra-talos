# Runbook: cluster rebuild with volume reclaim

Tear down, rebuild, re-attach every democratic-csi volume. Works because
`reclaimPolicy: Retain` keeps TrueNAS data and a PV's `spec.csi.volumeHandle`
re-mounts the same dataset/zvol.

> Object-level reclaim only. No protection against data loss on TrueNAS itself
> (VolSync/restic = future). Node-local PVs (Kafka, Ollama cache) are not
> reclaimable — [node loss](node-loss.md).

## 0. Preconditions

```sh
# every democratic-csi PV must be Retain
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy,SC:.spec.storageClassName
task pv:patch-retain    # if any say Delete
```

## 1. Export

```sh
task pv:export          # backups/pv/persistentvolumes.yaml + persistentvolumeclaims.yaml
git add backups/pv && git commit -m "chore: pv export before rebuild"
```

Check: every PV present, each has `spec.csi.volumeHandle`, PVC namespaces right.

## 2. Teardown

Private Omni repo: `omnictl cluster template delete -f cluster/homelab/omni-cluster.yaml`.
Optional: confirm datasets/zvols still exist on TrueNAS.

## 3. Rebuild

```sh
# private Omni repo: omnictl cluster template sync -f cluster/homelab/omni-cluster.yaml
task cluster:kubeconfig
task bootstrap            # CRDs, then cilium → coredns → cert-manager → flux
# private Omni repo: task cluster:seed-secrets   (ESO bitwarden-cli login)
```

## 4. Reclaim — order matters

Before Flux reconciles the apps, or they create fresh empty PVCs.

```sh
kubectl get pvc -A -L kustomize.toolkit.fluxcd.io/name
flux suspend kustomization frigate ollama hindsight postgres grafana-instance kube-prometheus-stack -n flux-system
# + the bank0-platform Kustomizations for the bank0 Postgres clusters

kubectl apply -f backups/pv/persistentvolumes.yaml
kubectl get pv -o name | xargs -I{} kubectl patch {} --type json \
  -p '[{"op":"remove","path":"/spec/claimRef/uid"},{"op":"remove","path":"/spec/claimRef/resourceVersion"}]' 2>/dev/null || true
kubectl apply -f backups/pv/persistentvolumeclaims.yaml   # namespaces must exist
kubectl get pvc -A                                         # every PVC Bound to its ORIGINAL PV
flux resume kustomization frigate ollama hindsight postgres grafana-instance kube-prometheus-stack -n flux-system
```

## 5. Post-checks

```sh
flux get kustomizations -A
kubectl get pv                     # all Bound, none Released
```

| Symptom | Cause | Fix |
|---|---|---|
| PVC `Pending`, new PV appears | PVC before PV, or stale claimRef | delete new PVC+PV, redo step 4 |
| PV `Released` | stale claimRef UID | claimRef patch, PVC re-binds |
| Mount fails | stale iSCSI session from old cluster | check TrueNAS targets; reboot node |
| App starts empty | bound a fresh volume | suspend, fix binding; old data still on TrueNAS |
