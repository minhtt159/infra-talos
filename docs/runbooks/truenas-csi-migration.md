# Runbook: democratic-csi → truenas-csi

Replace democratic-csi with the official [truenas-csi](https://github.com/truenas/truenas-csi)
driver (NFS + iSCSI; NVMe-oF not planned), then upgrade TrueNAS 25.10 → 27.
Scaffold: [`kubernetes/apps/truenas-csi/`](../../kubernetes/apps/truenas-csi/) (Flux
Kustomization `suspend: true` until Phase 1).

**Why move now:** democratic-csi `next` dropped every TrueNAS release before 26/27
(democratic-csi/democratic-csi#509), and our freenas-api drivers speak REST, which
TrueNAS 26+ removes. **democratic-csi has to be gone before the TrueNAS upgrade.**

**Why truenas-csi over tns-csi:** vendor-maintained alongside the API it calls; uses
the host's `iscsiadm` via nsenter, so Talos upgrades don't have to match a bundled
open-iscsi. tns-csi can adopt democratic-csi volumes in place but is single-maintainer
and self-declared not production-ready.

## Feature cross-check (what we use today vs truenas-csi 1.4.0)

| Feature | democratic-csi (today) | truenas-csi 1.4.0 | Action |
|---|---|---|---|
| iSCSI RWO, xfs | yes | yes (`csi.storage.k8s.io/fstype: xfs`) | set in SC |
| NFS RWX, `noatime,nfsvers=4` | yes | yes (SC `mountOptions` → mount flags) | set in SC |
| Retain + online expansion | yes | yes (chart default reclaim is `Delete`) | set `Retain` |
| Thin zvols | via driver config | `sparse` param, **default thick** | set `sparse: "true"` |
| Snapshots / restore / clone | yes, `detachedSnapshots` (zfs send/recv copy) | yes, plain ZFS snapshot + clone (clone pins its snapshot; destroy is deferred) | **gap:** no detached snapshots — fine for us, nothing consumes VolumeSnapshots yet |
| One VolumeSnapshotClass per driver | two | one (protocol-agnostic) | `truenas-csi` |
| Volume handle | PV name, parent dataset from the private config | **full dataset path** (`<pool>/k8s-iscsi/shares/pvc-…`) | better for the rebuild runbook |
| Import / static PV | n/a | not documented; code rebuilds target/export info from TrueNAS by dataset path | test in Phase 2 |
| Deterministic names (ns/pvc) | no | no (truenas/truenas-csi#76): dataset = provisioner's `pvc-<uid>`; the chart already passes `--extra-create-metadata`, the driver ignores it | migrated volumes: rename on adoption (Phase 3); new PVCs: upstream |
| NFS ownership | per our driver config | default `mapall root:wheel`; `nfs.rootSquash: "false"` + `fsGroup` for chown-sensitive apps | test per app |
| NFS/iSCSI host allow-lists | per our driver config | `nfs.hosts`/`nfs.networks`, `iscsi.initiators` | LAN CIDRs are topology — keep out of git (Secret via `valuesFrom` if needed) |
| CHAP | not used | yes, but secrets are plaintext SC params (PR #46 open) | don't use yet |
| Talos | env hacks (`ISCSIADM_HOST_*`) | works, **needs `iscsi-dir` hostPath patch** (#80, #84) | postRenderer in HelmRelease |
| Chart as OCI | yes | no (#83) | `HelmRepository` (legacy exception) |
| Sidecar resource values | partial | none | Kyverno PolicyException (shared with democratic-csi) |
| Metrics | no | controller `/metrics` + ServiceMonitor | enabled |
| StorageClass snapshot schedules | no | `snapshot.*` params | optional later, instead of TrueNAS periodic tasks |

## Upstream state (GitHub, 2026-10-31; re-checked 2026-11-08, no change)

v1.4.0 still the latest release; #76, #80, #83, #84 still open (#80: 8 comments, no
maintainer fix).

- **Open, no maintainer reply:** #80 Talos node pods stuck on `/etc/iscsi` hostPath check
  (since Oct 15); #84 same root cause; #83 OCI chart; #76 deterministic volume identity.
- **Recently fixed, 1.2–1.4:** Talos `iscsiadm` path (#56), iSCSI connector files lost
  on node-pod restart (#55), WebSocket auth lost after long uptime (#54), slow-appliance
  staging retries (#74), snapshot leaks (#69). The iSCSI/session code is young, so pin it
  and test each bump before merging Renovate's PR.
- **How changes land:** one main maintainer ships squashed release PRs (v1.2.0…v1.4.0).
  External PRs mostly get closed unmerged and reimplemented in house (#70 proxy/CA →
  v1.4.0; #44 OCI publishing closed), or sit open for months (#24, #46, #48, #49).
- **Rollback risk:** the Helm index on `master` lists only 1.3.0 and 1.4.0, so an older
  pinned version may disappear.
- License: repo is GPL-3.0; the chart's artifacthub annotation says Apache-2.0.

## Contributing upstream

Yes, but open an issue first; don't lead with a PR. Our setup (Flux + Talos + Kyverno)
is the use case the issues above are missing.

1. **#80/#84 (Talos):** comment with our Flux `postRenderers` repro and propose a
   `node.iscsiDirHostPathType` value (or `DirectoryOrCreate`). It's a one-line chart change.
2. **#83 (OCI chart):** add our use case: Flux `OCIRepository`, Renovate.
3. **New issue:** `resources` values for the CSI sidecars, so policy engines don't need exceptions.
4. **#76 (deterministic names):** propose a StorageClass `datasetNameTemplate` parameter
   (`${pvc.metadata.namespace}-${pvc.metadata.name}`, csi-driver-nfs style). The pieces exist:
   `--extra-create-metadata` is on, `CreateVolume` only needs to prefer the template over
   `req.Name`, and the existing-dataset branch already handles reuse.
5. **New issue:** a way to disable NVMe-oF. The driver derives a portal and calls
   `nvmet.port.create` at startup even when no class uses it (a config write on the appliance).
6. **After Phase 2:** if static-PV adoption works, write it up (docs, or #76).

Expect the fix to ship in a release PR rather than as our PR merged.

## Phase 0: prerequisites (TrueNAS 25.10)

- [x] TrueNAS: API key (dedicated user if the role model allows it), iSCSI + NFS services on
      (both already serve democratic-csi).
- [x] Parent datasets: reuse democratic-csi's `<pool-iscsi>/k8s-iscsi/shares` and
      `<pool-nfs>/k8s-nfs/shares` (`datasetPath` in the HelmRelease). Both drivers create
      one child dataset/zvol + share/target per volume and never touch siblings, so sharing
      the parent is safe; it keeps adopted and new volumes under one path. The `…/snaps`
      datasets are democratic-csi's detached snapshots; truenas-csi doesn't use them.
- [x] TLS: the cert must match the host in `url`. Verified 2026-11-09: Let's Encrypt cert on
      the `url` host, so `insecureSkipTLS: false` stays.
- [x] Vaultwarden item `homelab-talos/truenas-csi` with fields `api-key`, `url`
      (`wss://<host>/api/current`), `pool-iscsi` and `pool-nfs`: **bare pool names**, one
      per protocol; the SC `pool` parameter overrides `truenas.defaultPool`. The driver
      checks both with `pool.query` (startup + CreateVolume), so a dataset path in there
      crashloops the pods. UUID is in `app/externalsecret.yaml`.
- [x] Pin democratic-csi off the floating `next` tag, to the digest running now
      (`kubectl -n democratic-csi get pods -o jsonpath='{..imageID}'`), so a node
      reprovision can't pull a TN26-only image. Done: `next@sha256:0f308ae6…` (2026-11-08).

## Phase 1: deploy side by side

- [x] Drop `suspend: true` from `truenas-csi/ks.yaml`.
- [x] `kubectl -n truenas-csi get pods`: controller 6/6, node 3/3 on every node (2026-11-09).
- [x] `kubectl get csinode -o yaml | grep csi.truenas.io` on every node; `kubectl get sc`.

Startup log, both expected:
- `Failed to resolve/create NVMe-oF port, will retry on first use ... Invalid params`: 1.4.0
  always derives an NVMe-oF portal from `url` and tries `nvmet.port.create` at startup; no
  value turns it off. Harmless while no StorageClass uses `protocol: nvmeof`.
- `Configured iSCSI IQN base differs from the TrueNAS appliance basename`: the appliance
  basename wins, same one democratic-csi targets use.

## Phase 2: smoke tests (throwaway namespace)

All run 2026-11-09 in `truenas-csi-smoke` (deleted afterwards), truenas-csi 1.4.0.

- [x] iSCSI PVC + pod: write, delete pod, re-read on another node; expand online. xfs,
      attach+mount 6–7s, node move 9s, resize 73s (controller 1s, the rest kubelet).
      Non-root pods need `fsGroup` (xfs root is 0:0; CSIDriver `fsGroupPolicy: File`).
      Extent name is the dataset path cut at 64 chars, so a long pool name loses the UUID's
      tail; lookups go by zvol path, so cosmetic.
- [x] VolumeSnapshot → restore PVC → data matches. Snapshot is `<dataset>@snapshot-<uid>`,
      CreateSnapshot took 52s; restore is a sibling clone, bound in 5s.
- [x] NFS PVC: nfs4.2 `noatime`. Default share is `mapall root:wheel`: a uid-1000 pod
      writes fine, files show as 0:0; with `fsGroup: 1000` the dir is `0:1000` setgid.
      RWX across two nodes works.

      **NFS permission model (decided 2026-11-09).** democratic-csi shares are
      `maproot root:root` (no_root_squash) on `0777` datasets with no host allow-list.
      truenas-csi `truenas-csi-nfs` keeps the chart's `mapall root:wheel` (any pod uid
      writes, files 0:0, datasets stay 755) and adds `nfs.networks: <node subnet>`. The
      real control on either driver is the allow-list, not the uid mapping. Mapall to an
      unprivileged user doesn't work in 1.4.0: the driver never chowns the dataset, so the
      mapped user can't write and fsGroup's chown is squashed. Ownership-sensitive NFS
      apps (none today) get a separate class with `nfs.rootSquash: "false"`. SC params
      are immutable: changing one means deleting the class while no PV uses it.
- [x] Delete PVC → PV `Released`, no DeleteVolume in the log (Retain). Patching the PV to
      `Delete` afterwards removes dataset + share/target in ~5s: that is the cleanup path.
- [x] Controller rollout restart (9s) and node-pod delete (3s) under a 1 Hz writer: no gap
      over 2s; new attach on that node right after: 14s.
- [x] **Static-PV adoption** of throwaway democratic-csi volumes, iSCSI and NFS: works
      zero-copy, data intact. PV shapes below. What the driver actually does:
      - **ControllerPublish creates nothing.** It looks the extent up by zvol path (iSCSI) or
        reads the dataset mountpoint (NFS) and reuses democratic's target/extent/share as
        they are. `targetIQN` in `volumeAttributes` is ignored. No extent or share → publish
        fails. So the adopted volume keeps democratic's initiator group and share settings
        (no `mapall`: files keep real uid/gid, unlike new truenas-csi NFS volumes).
      - **Readable names are not free.** A `zfs rename` alone breaks the mount, because the
        extent's disk path / the share path still point at the old name. Per volume on
        TrueNAS: rename dataset → edit the extent `disk` (iSCSI) or the share path (NFS) → PV
        with the new handle. Or keep `pvc-<uid>` and skip the rename.
      - **DeleteVolume on an adopted volume** (only if the PV is `Delete`) removes democratic's
        target + extent (or share), then the dataset recursively; shared initiator/portal
        groups stay while another target uses them. Target/extent/share delete errors are
        non-fatal and logged only at debug.

Static PV + PVC for adoption (pool names live in Vaultwarden, never here):

```yaml
apiVersion: v1
kind: PersistentVolume
metadata: {name: <app>-data}
spec:
  accessModes: [ReadWriteOnce]          # NFS: ReadWriteMany, plus mountOptions: [noatime, nfsvers=4]
  capacity: {storage: <size>}
  persistentVolumeReclaimPolicy: Retain
  storageClassName: truenas-csi-iscsi   # or truenas-csi-nfs
  volumeMode: Filesystem
  claimRef: {apiVersion: v1, kind: PersistentVolumeClaim, namespace: <ns>, name: <pvc>}
  csi:
    driver: csi.truenas.io
    fsType: xfs                         # NFS: omit
    volumeHandle: <pool>/k8s-iscsi/shares/<dataset>      # NFS: <pool>/k8s-nfs/shares/<dataset>
    volumeAttributes:
      protocol: iscsi                   # NFS: nfs, nfsServer: truenas.hnimn.art,
      pool: <pool>                      #      nfsPath: /mnt/<pool>/k8s-nfs/shares/<dataset>
      datasetPath: k8s-iscsi/shares
      lun: "0"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata: {name: <pvc>, namespace: <ns>}
spec:
  accessModes: [ReadWriteOnce]
  storageClassName: truenas-csi-iscsi
  volumeName: <app>-data
  resources: {requests: {storage: <size>}}
```

Smaller findings: NFS PVs get `fsType: xfs` from the provisioner's `--default-fstype`
(cosmetic); the controller `rollout restart` left a `restartedAt` annotation (Helm drift,
harmless).

## Phase 3: migrate workloads

Order: low risk first. Method **A** = static-PV adoption (Phase 2 passed), **B** = copy.
Naming (decided 2026-11-09): **keep the `pvc-<uid>` dataset names**; only the PV name is
readable (`<app>-data`). Renaming would cost an extent/share path edit on TrueNAS per volume
(see Phase 2) for no functional gain; revisit when #76 lands upstream. Adopted NFS volumes
keep real uid/gid, new ones get `mapall`.
For copies, a `pv-migrate`/rsync Job is fine for small volumes; for large ones,
`zfs send | zfs recv` on TrueNAS into the dataset of a freshly provisioned PVC
(test it on a throwaway first). Each step: suspend the app (Flux), migrate, switch
`storageClassName` in git, resume.

| Workload | Class today | → | Notes |
|---|---|---|---|
| alertmanager (kube-prometheus-stack) | ~~truenas-nfs~~ | truenas-csi-nfs | **done 2026-11-09**: SC switched in git, old PVC + pod deleted, operator recreated both. Old PV patched to Delete: democratic's DeleteVolume **failed** (`filesystem has dependent snapshots`, a TrueNAS snapshot task on the parent) but the PV object went away anyway, so dataset `k8s-nfs/shares/pvc-ca827d8b-…` + its share are orphaned → delete by hand |
| grafana | truenas-iscsi | truenas-csi-iscsi | small; A or B |
| hindsight, yoke, frigate config | truenas-iscsi | truenas-csi-iscsi | A or B |
| frigate media | truenas-nfs | truenas-csi-nfs | large: A, or zfs send/recv |
| postgres, bank0-staging, bank0-production | truenas-iscsi | truenas-csi-iscsi | CNPG, see below |

**Old-volume cleanup gotcha.** democratic-csi's DeleteVolume refuses a dataset that has
snapshots (TrueNAS periodic tasks on `k8s-*/shares` make that every dataset), and its old
external-provisioner (v3.6.0) doesn't hold the PV finalizer, so `kubectl delete pv` succeeds
while the dataset and share stay. Either destroy snapshots first on TrueNAS, or leave old PVs
`Released`/Retain and clean them up in one TrueNAS pass in Phase 4. truenas-csi's own
DeleteVolume is `recursive + force`, so this only affects democratic volumes.

StatefulSet `volumeClaimTemplates` (alertmanager, CNPG) can't change in place. Delete
the StatefulSet with `--cascade=orphan` or let the operator recreate it, then replace
the PVC.

### CNPG (postgres, bank0-*)

Don't copy PGDATA files. Use CNPG's own replica swap; it needs no adoption and costs
a switchover's seconds of downtime:

1. Backup first. postgres: on-demand `Backup` (barman-cloud). **bank0-production has no
   backups**: take a `pg_dump` (or add an ObjectStore) before touching it.
2. In git, set `storage.storageClass` **and** `walStorage.storageClass` to
   `truenas-csi-iscsi`, and `instances: 2`. CNPG never moves existing PVCs, so the
   primary stays put, while the new replica gets fresh PVCs on the new class from the
   current spec.
3. Wait until the replica is streaming (`kubectl cnpg status <cluster>`), then
   `kubectl cnpg promote <cluster> <new-instance>`.
4. Set `instances: 1` again. CNPG removes the remaining replica (the old instance)
   and its PVCs, whose PVs go to `Released` (Retain) and stay on TrueNAS until deleted
   by hand. Better: stay at `instances: 2` with anti-affinity, which the `ponytail`
   comments already ask for.
5. `database/postgres/ks.yaml`: change `dependsOn` from `democratic-iscsi` to
   `truenas-csi` (namespace `truenas-csi`).

Keep Postgres on iSCSI; don't use NFS for PGDATA.

## Phase 4: decommission democratic-csi

- [ ] Adopted volumes stay on democratic's targets/shares; they only go when their PV is
      deleted with `Delete`. Leave them, they are plain TrueNAS objects now.
- [ ] No PV left with `org.democratic-csi.*`: `kubectl get pv -o custom-columns=NAME:.metadata.name,DRIVER:.spec.csi.driver`.
- [ ] Remove `kubernetes/apps/democratic-csi/`, its Kyverno entries (`policies.yaml`
      exclude list, `policyexceptions.yaml`), the Taskfile regex half, and the
      `dependsOn` references. Rename the classes in docs.
- [ ] Update [storage.md](../storage.md), [cluster-rebuild.md](cluster-rebuild.md), README.
- [ ] On TrueNAS: delete old zvols/datasets, targets/extents and NFS shares once verified.
      Old and new volumes share the `shares` parents, so go per volume: a child dataset
      with no matching `kubectl get pv` handle is democratic's leftover. Destroy its
      snapshots first (that is what blocked democratic's own delete). Then drop the
      `…/snaps` datasets. Delete the two `homelab-talos/truenas-{iscsi,nfs}` Vaultwarden items.

      Known leftovers so far (decided 2026-11-09: no per-volume cleanup, one sweep here):
      - `k8s-nfs/shares/pvc-ca827d8b-fce0-4ec0-adf7-c5e890bd1a7d` + its NFS share (alertmanager)

## Phase 5: TrueNAS 25.10 → 27

- [ ] Only after Phase 4 (REST is gone in 26+).
- [ ] Check truenas-csi release notes/issues for 27 support. `url` points at
      `/api/current`, which follows the appliance's version; a pinned versioned
      endpoint would be safer, if the driver accepts one.
- [ ] Reports (unverified) say the 26 upgrade revokes API keys. If so, mint a new key
      and update the Vaultwarden item; the pods read the Secret only at startup, so run
      `kubectl -n truenas-csi rollout restart deploy,ds`.
