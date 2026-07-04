# Runbook: Turing RK1 nodes (turing-01 / turing-03)

RK1 boards live in the Turing Pi 2 board (BMC at `10.1.80.99`, creds in `.env`:
`TPI_HOSTNAME` / `TPI_USERNAME` / `TPI_PASSWORD`, used by the `tpi` CLI).

Layout: **Talos is installed on each board's NVMe** (`install.disk` pinned
by-id in `bootstrap/homelab/omni-cluster.yaml`). The RK3588 boot ROM cannot
boot NVMe by itself — the **sbc-rockchip overlay (U-Boot)** flashed to the
board is what chain-boots the NVMe.

Docs: <https://docs.siderolabs.com/talos/v1.13/platform-specific-installations/single-board-computers/turing_rk1#booting-from-usb-or-nvme>

## Installation media rules

- Generate media from Omni (omni.hnimn.art) → *Download Installation Media* →
  **Turing RK1 (arm64)**.
- **Match the cluster's Talos version** (see `talos.version` in
  `omni-cluster.yaml`). A mismatched (older) image boots but immediately needs
  an upgrade cycle.
- **Use plain WireGuard, NOT the gRPC tunnel.** The tunnel's userspace
  WireGuard is broken on RK1 (`Failed to write packets to TUN device:
  input/output error`) — machine registers with Omni but apid never gets its
  CSR signed and the node never joins. Plain kernel WireGuard (UDP to the Omni
  VM, `SIDEROLINK_WIREGUARD_ADVERTISED_ADDR` in omni-selfhosted) works.

## Install / reinstall

1. Prep the NVMe with the Talos image (should already be done; otherwise `dd`
   the image onto the NVMe from another computer).
2. Download the sbc-rockchip overlay and flash it to the node:

   ```sh
   set -a; source .env; set +a
   tpi flash -n <slot> -i <image>
   tpi power on -n <slot>
   ```

3. Board boots into maintenance mode and registers with Omni.
4. **Reflash changes the machine UUID** (U-Boot generates it) — update the
   UUID in `omni-cluster.yaml` (Workers list + its `kind: Machine` block),
   then `task cluster:sync`. Omni installs to the pinned NVMe and joins.

## Recovery: wipe and return to maintenance mode

When a node is wedged (stale install on NVMe, wrong cluster secrets, etc.):

1. `ssh` into the Turing Pi BMC.
2. `picocom /dev/ttyS<X> -b 115200` (node's serial port).
3. Interrupt the U-Boot sequence at boot.
4. Choose wipe disk → node returns to maintenance mode.

Serial console without ssh: `tpi uart -n <slot> get` dumps the boot log —
first thing to check when a node is stuck (look for volume mount failures,
TUN errors, CSR/certificate errors).

## Gotchas seen in the field (July 2026 rebuild)

- `tpi flash` may fail with `No supported USB devices found` if the BMC's USB
  mux is still routed elsewhere — power the node off and retry.
- RK1 has an RTC but it can boot with a 1970 clock; NTP jumps it ~56 years
  during boot. Harmless by itself.
- `structure needs cleaning` on a volume = corrupted XFS from a previous
  life — wipe that partition/disk before rejoining.
- Removing a machine from the cluster template requires removing BOTH the
  Workers/ControlPlane list entry AND its `kind: Machine` document (and the
  `---` separator — an empty YAML doc fails template validation).
