# Cluster hardware

Six Talos machines managed by Omni (`bootstrap/homelab/omni-cluster.yaml` is
the source of truth for UUIDs and install disks).

| Machine | Role | Hardware | CPU/RAM | Disk | Notes |
|---|---|---|---|---|---|
| mini-talos-01 | control plane | Minisforum UM450, bare metal | 32GB | 512GB SSD (ESO512G) | no Proxmox |
| mini-talos-02 | control plane | Minisforum UM450, bare metal | 32GB | 512GB SSD (WD SN550) | no Proxmox |
| mini-talos-03 | control plane | Proxmox VM | 6 cores / 28GB | 1TB NVMe passthrough (WD SN750) | qemu-guest-agent |
| turing-01 | worker | Turing RK1 (arm64), slot 1 | 32GB | 512GB NVMe (WD SN550) | Coral TPU (gasket), boots via eMMC U-Boot |
| turing-03 | worker | Turing RK1 (arm64), slot 3 | 32GB | 512GB NVMe (WD SN550) | boots via eMMC U-Boot |
| mini-talos-04 | worker | Proxmox VM | 4 cores / 16GB | 1TB NVMe passthrough (WD SN750) | Intel Arc B580 GPU passthrough (xe), qemu-guest-agent |

Supporting infrastructure:

- **Turing Pi 2** board hosts the RK1s — BMC at `10.1.80.99` (`tpi` CLI, creds
  in `.env`). See `docs/runbooks/rk1-nodes.md`.
- **Proxmox** box hosts mini-talos-03/04 VMs and the **Omni VM**
  (`omni.${SECRET_DOMAIN}` = `10.1.80.15`, deployed from its own compose repo).
- Network: everything on `10.1.80.0/24` (UniFi UDM SE).

Install disks are pinned by-id (serials via `task disks`) — raw `/dev/nvmeXn1`
names renumber when PCIe topology changes, which the B580 passthrough on
mini-talos-04 makes a real risk.
