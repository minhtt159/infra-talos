# Storage

- **openebs** — node-local (`hostpath`) volumes. A PV here is pinned to one
  node and dies with it. Only Kafka uses it (`openebs-hostpath-sata`, pinned to
  the `storage=sata` node) and accepts that loss — recovery is in the
  KafkaNodePool comments.
- **Node rotation** — every other stateful PV (Postgres, Grafana, Ollama,
  Frigate, …) lives on TrueNAS, so replacing a node is a pod reschedule.
  Metrics are not stored in-cluster: Prometheus runs in agent mode and
  remote-writes to `promeo` (Prometheus on TrueNAS).
- **democratic-csi** — dynamic PVs backed by a **TrueNAS** appliance over
  **iSCSI** (block) and **NFS** (shared). TrueNAS credentials come from Vaultwarden
  via an `ExternalSecret`. See [`democratic-csi/README.md`](../kubernetes/apps/democratic-csi/README.md).
- **Rebuild survival** — both TrueNAS storage classes use
  `reclaimPolicy: Retain`; volumes are reclaimed after a full cluster
  recreation via `task pv:export` + the
  [cluster-rebuild runbook](runbooks/cluster-rebuild.md).
