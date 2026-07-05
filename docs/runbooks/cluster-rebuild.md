# Runbook: full cluster rebuild with volume reclaim

Goal: tear the cluster down and rebuild it while re-attaching every
democratic-csi volume (TrueNAS NFS datasets + iSCSI zvols) to its app.

Works because:
- `reclaimPolicy: Retain` — deleting PVC/cluster never deletes TrueNAS data.
- A PV manifest pins `spec.csi.volumeHandle` → re-applying the *same* PV
  object makes the CSI driver mount the *same* dataset/zvol.

> Future upgrade path: VolSync (restic) for data-level backup/restore.
> This runbook only covers object-level reclaim — it does NOT protect
> against data deletion/corruption on TrueNAS itself.

## 0. Preconditions (verify BEFORE teardown)

```sh
# every democratic-csi PV must be Retain — Delete here means data loss on teardown
kubectl get pv -o custom-columns=NAME:.metadata.name,RECLAIM:.spec.persistentVolumeReclaimPolicy,SC:.spec.storageClassName

# if any still say Delete (created before the Retain change):
task pv:patch-retain
```

## 1. Export state

```sh
task pv:export        # writes backups/pv/persistentvolumes.yaml + persistentvolumeclaims.yaml
git add backups/pv && git commit -m "chore: pv export before rebuild"  # commit = your parachute
```

Sanity-check the export: every expected PV present, each has
`spec.csi.volumeHandle`, PVC namespaces look right.

## 2. Teardown

```sh
# Teardown = deleting the Omni cluster. That lives in the private Omni repo
# (omni-selfhosted), not here:
#   omnictl cluster template delete -f cluster/homelab/omni-cluster.yaml
```

TrueNAS check (optional but calming): datasets/zvols still exist under the
democratic-csi parent dataset.

## 3. Rebuild

```sh
# 1. Re-provision nodes from the private Omni repo (omni-selfhosted):
#      omnictl cluster template sync -f cluster/homelab/omni-cluster.yaml
#    (or push to cluster/** → the cluster-sync workflow). Then, back in this repo:
task cluster:kubeconfig
task bootstrap            # CRDs, then cilium → coredns → cert-manager → flux
```

Then apply the SOPS age key secret if it is not seeded by bootstrap
(kustomize-controller needs it to decrypt the bitwarden-cli bridge secret):

```sh
sops -d bootstrap/sops-age.sops.yaml | kubectl apply -f -
```

## 4. Reclaim volumes — ORDER MATTERS

Do this **before** (or immediately after) Flux reconciles the app
Kustomizations, otherwise apps create fresh empty PVCs that bind to fresh
volumes.

```sh
# 4a. suspend the stateful apps so they don't race you
flux suspend kustomization frigate ollama    # extend list as stateful apps grow

# 4b. PVs first (cluster-scoped, no deps)
kubectl apply -f backups/pv/persistentvolumes.yaml

# 4c. clear stale claimRefs so re-created PVCs can bind
#     (exported claimRef points at old PVC UIDs — kubectl may reject or PV stays Released)
kubectl get pv -o name | xargs -I{} kubectl patch {} --type json \
  -p '[{"op":"remove","path":"/spec/claimRef/uid"},{"op":"remove","path":"/spec/claimRef/resourceVersion"}]' 2>/dev/null || true

# 4d. PVCs (namespaces must exist — Flux creates them, or apply namespace.yaml manually)
kubectl apply -f backups/pv/persistentvolumeclaims.yaml

# 4e. verify every PVC is Bound to its ORIGINAL PV
kubectl get pvc -A

# 4f. resume
flux resume kustomization frigate ollama
```

## 5. Post-checks

```sh
flux get kustomizations -A          # all Ready
kubectl get pv                      # all Bound, none Released
# spot-check one app's data (e.g. frigate recordings present)
```

## Failure modes

| Symptom | Cause | Fix |
|---|---|---|
| PVC `Pending`, new PV appears | PVC applied before PV, or claimRef stale | delete new PVC+PV, redo 4b–4d |
| PV `Released` | stale claimRef UID | step 4c patch, PVC re-binds |
| Mount fails on node | iSCSI target still logged in from old cluster | TrueNAS: check associated targets; node: reboot clears stale sessions |
| App starts empty | it bound a fresh volume | suspend app, fix binding, old data still on TrueNAS — nothing lost |
