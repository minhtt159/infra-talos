# Storage

- **openebs** — node-local volumes for scratch / non-replicated data.
- **democratic-csi** — dynamic PVs backed by a **TrueNAS** appliance over
  **iSCSI** (block) and **NFS** (shared). TrueNAS credentials come from Vaultwarden
  via an `ExternalSecret`. See [`democratic-csi/README.md`](../kubernetes/apps/democratic-csi/README.md).
- **Rebuild survival** — both TrueNAS storage classes use
  `reclaimPolicy: Retain`; volumes are reclaimed after a full cluster
  recreation via `task pv:export` + the
  [cluster-rebuild runbook](runbooks/cluster-rebuild.md).
