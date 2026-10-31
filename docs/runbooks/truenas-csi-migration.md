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
| Volume handle | PV name, parent dataset from the private config | **full dataset path** (`<pool>/truenas-csi/iscsi/pvc-…`) | better for the rebuild runbook |
| Import / static PV | n/a | not documented; code rebuilds target/export info from TrueNAS by dataset path | test in Phase 2 |
| Deterministic names (ns/pvc) | no | no (truenas/truenas-csi#76) | — |
| NFS ownership | per our driver config | default `mapall root:wheel`; `nfs.rootSquash: "false"` + `fsGroup` for chown-sensitive apps | test per app |
| NFS/iSCSI host allow-lists | per our driver config | `nfs.hosts`/`nfs.networks`, `iscsi.initiators` | LAN CIDRs are topology — keep out of git (Secret via `valuesFrom` if needed) |
| CHAP | not used | yes, but secrets are plaintext SC params (PR #46 open) | don't use yet |
| Talos | env hacks (`ISCSIADM_HOST_*`) | works, **needs `iscsi-dir` hostPath patch** (#80, #84) | postRenderer in HelmRelease |
| Chart as OCI | yes | no (#83) | `HelmRepository` (legacy exception) |
| Sidecar resource values | partial | none | Kyverno PolicyException (shared with democratic-csi) |
| Metrics | no | controller `/metrics` + ServiceMonitor | enabled |
| StorageClass snapshot schedules | no | `snapshot.*` params | optional later, instead of TrueNAS periodic tasks |

## Upstream state (GitHub, 2026-10-31)

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
4. **After Phase 2:** if static-PV adoption works, write it up (docs, or #76).

Expect the fix to ship in a release PR rather than as our PR merged.

## Phase 0: prerequisites (TrueNAS 25.10)

- [ ] TrueNAS: API key (dedicated user if the role model allows it), iSCSI + NFS services on,
      parent datasets `<pool>/truenas-csi/iscsi` and `<pool>/truenas-csi/nfs`.
- [ ] TLS: the cert must match the host in `url`. If it's still the stock self-signed cert, set
      `insecureSkipTLS: true` or `truenas.caBundle`.
- [ ] Vaultwarden item `homelab-talos/truenas-csi` with fields `api-key`, `url`
      (`wss://<host>/api/current`) and `pool`. Replace the 3 TODO UUIDs in
      `app/externalsecret.yaml`.
- [ ] Pin democratic-csi off the floating `next` tag, to the digest running now
      (`kubectl -n democratic-csi get pods -o jsonpath='{..imageID}'`), so a node
      reprovision can't pull a TN26-only image.

## Phase 1: deploy side by side

- [ ] Drop `suspend: true` from `truenas-csi/ks.yaml`.
- [ ] `kubectl -n truenas-csi get pods`: controller 6/6, node 3/3 on every node.
- [ ] `kubectl get csinode -o yaml | grep csi.truenas.io` on every node; `kubectl get sc`.

## Phase 2: smoke tests (throwaway namespace)

- [ ] iSCSI PVC + pod: write, delete pod, re-read on another node (drain); expand online.
- [ ] VolumeSnapshot → restore PVC → data matches.
- [ ] NFS PVC with a non-root pod (and one with `fsGroup`): check ownership with the default `mapall`.
- [ ] Delete PVC → PV `Released`, dataset still on TrueNAS (Retain).
- [ ] Restart the controller/node pods mid-attach; the volume stays usable.
- [ ] **Static-PV adoption** of a throwaway democratic-csi volume (one iSCSI, one NFS):
      scale down → PV to Retain → delete PVC + PV → create a PV with
      `csi.driver: csi.truenas.io`, `volumeHandle: <pool>/<democratic dataset path>`,
      same `volumeMode`/`fsType`, `claimRef` → PVC → mount. If this works, Phase 3
      becomes zero-copy. Watch whether ControllerPublish rewrites the democratic
      target's initiator group / NFS share hosts, and what `DeleteVolume` would remove.

## Phase 3: migrate workloads

Order: low risk first. Method **A** = static-PV adoption (if Phase 2 passed), **B** = copy.
For copies, a `pv-migrate`/rsync Job is fine for small volumes; for large ones,
`zfs send | zfs recv` on TrueNAS into the dataset of a freshly provisioned PVC
(test it on a throwaway first). Each step: suspend the app (Flux), migrate, switch
`storageClassName` in git, resume.

| Workload | Class today | → | Notes |
|---|---|---|---|
| alertmanager (kube-prometheus-stack) | truenas-nfs | truenas-csi-nfs | 1Gi, disposable: just recreate |
| grafana | truenas-iscsi | truenas-csi-iscsi | small; A or B |
| hindsight, yoke, frigate config | truenas-iscsi | truenas-csi-iscsi | A or B |
| frigate media | truenas-nfs | truenas-csi-nfs | large: A, or zfs send/recv |
| postgres, bank0-staging, bank0-production | truenas-iscsi | truenas-csi-iscsi | CNPG, see below |

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

- [ ] No PV left with `org.democratic-csi.*`: `kubectl get pv -o custom-columns=NAME:.metadata.name,DRIVER:.spec.csi.driver`.
- [ ] Remove `kubernetes/apps/democratic-csi/`, its Kyverno entries (`policies.yaml`
      exclude list, `policyexceptions.yaml`), the Taskfile regex half, and the
      `dependsOn` references. Rename the classes in docs.
- [ ] Update [storage.md](../storage.md), [cluster-rebuild.md](cluster-rebuild.md), README.
- [ ] On TrueNAS: delete old zvols/datasets, targets/extents and NFS shares once verified.
      Delete the two `homelab-talos/truenas-{iscsi,nfs}` Vaultwarden items.

## Phase 5: TrueNAS 25.10 → 27

- [ ] Only after Phase 4 (REST is gone in 26+).
- [ ] Check truenas-csi release notes/issues for 27 support. `url` points at
      `/api/current`, which follows the appliance's version; a pinned versioned
      endpoint would be safer, if the driver accepts one.
- [ ] Reports (unverified) say the 26 upgrade revokes API keys. If so, mint a new key
      and update the Vaultwarden item; the pods read the Secret only at startup, so run
      `kubectl -n truenas-csi rollout restart deploy,ds`.
