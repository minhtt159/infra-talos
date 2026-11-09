# Runbook: democratic-csi → truenas-csi (pointer)

The cluster moved every TrueNAS-backed volume from democratic-csi to the official
[truenas-csi](https://github.com/truenas/truenas-csi) driver on 2026-11-09, by static-PV
adoption (zero copy) for plain PVCs and a replica swap for the CNPG clusters.

The full runbook (phases, results, gotchas, the TrueNAS-side cleanup list, the TrueNAS 27
upgrade) lives in the private `homelab-platform` repo at
`docs/truenas/truenas-csi-migration.md`, with the private topology filled in.

What stays here: the driver wiring in
[`kubernetes/apps/truenas-csi/`](../../kubernetes/apps/truenas-csi/), the
[storage overview](../storage.md), and the PV reclaim procedure in
[cluster-rebuild.md](cluster-rebuild.md).
