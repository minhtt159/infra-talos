# Networking & ingress

- **LoadBalancer IPs** — Cilium LB IPAM, two pools
  ([`cilium/app/networks.yaml`](../kubernetes/apps/kube-system/cilium/app/networks.yaml)):
  - `bgp` — routed VIP prefix `10.1.81.0/24`, **outside** the node subnet.
    Services opt in with the label `announce: bgp`; each VIP is advertised as a
    /32 over **eBGP to the UniFi gateway** only from nodes that hold a local
    endpoint ([`cilium/app/bgp.yaml`](../kubernetes/apps/kube-system/cilium/app/bgp.yaml)),
    so `externalTrafficPolicy: Local` never blackholes. This is the target state.
  - `pool` — legacy `10.1.80.10-49` inside the node subnet, announced over
    L2/ARP on `ens*`/`eth*`. Leader election ignores pod placement
    (cilium/cilium#27800) → blackholes with `externalTrafficPolicy: Local`.
    Goes away once both gateways sit on the `bgp` pool.
- **Router side (manual, UniFi UI → Routing → BGP, FRR config upload).**
  Cilium initiates the session, so the gateway can accept the node subnet as
  dynamic neighbours and node IPs may stay DHCP. Timers must match
  `CiliumBGPPeerConfig` (3/9). Verify with `cilium bgp peers` / `cilium bgp routes`.
  UniFi takes ONE FRR file per device and re-uploading bounces every session;
  `maximum-paths` is required for ECMP (UniFi FRR defaults to a single best path).

  ```
  router bgp 64512
   bgp router-id 10.1.80.1
   no bgp ebgp-requires-policy
   neighbor K8S peer-group
   neighbor K8S remote-as 64513
   neighbor K8S timers 3 9
   bgp listen range 10.1.80.0/24 peer-group K8S
   address-family ipv4 unicast
    neighbor K8S activate
    neighbor K8S soft-reconfiguration inbound
    maximum-paths 8
   exit-address-family
  exit
  ```

- **Migration (L2 → BGP)** — 1) merge BGP config, upload FRR config, confirm
  sessions `established` from every node; 2) expose a throwaway LB Service with
  `announce: bgp`, curl its VIP from another VLAN and from inside `10.1.80.0/24`;
  3) move `envoy-internal` then `envoy-external` (`infrastructure.labels` +
  new `lbipam.cilium.io/ips`) — external-dns rewrites the UniFi/Cloudflare
  records; update off-cluster consumers of the old VIPs (DNSControl records,
  VM egress allowlists); 4) delete `pool`, the L2 policy and `l2announcements`.
- **Gateways** (Envoy Gateway, Gateway API) —
  [`envoy-gateway/gateway/`](../kubernetes/apps/network/envoy-gateway/gateway):
  - `envoy-internal` → `10.1.80.11`, host `internal.${SECRET_DOMAIN}`
  - `envoy-external` → `10.1.80.12`, host `external.${SECRET_DOMAIN}`
  - both terminate TLS with the `${SECRET_DOMAIN}-production-tls` wildcard cert.
    Apps attach via `HTTPRoute` (see each app's `httproute.yaml`).
- **DNS** — `external-dns` publishes gateway hostnames to **Cloudflare**
  (`cloudflare-dns`) and **UniFi** (`unifi-dns`).
- **External access** — `cloudflare-tunnel` (cloudflared) exposes selected
  services without opening ports.
- **Certificates** — cert-manager `letsencrypt-production` ClusterIssuer
  (DNS-01 over 1.1.1.1) plus an `internal-ca` issuer.
