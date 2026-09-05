# Networking & ingress

- **LB VIPs** — Cilium LB IPAM pool `bgp` = routed prefix `10.1.81.0/24`, outside
  the node subnet ([`cilium/app/networks.yaml`](../kubernetes/apps/kube-system/cilium/app/networks.yaml)).
  Opt-in per Service: label `announce: bgp` (gateways: EnvoyProxy `envoyService.labels`).
- **BGP** — every node peers eBGP with the router ([`cilium/app/bgp.yaml`](../kubernetes/apps/kube-system/cilium/app/bgp.yaml)).
  A VIP is advertised as /32 only from nodes with a local endpoint, so
  `externalTrafficPolicy: Local` never blackholes. Router-side FRR config, runbooks
  and gotchas live in the private platform docs. Verify: `cilium bgp peers`,
  `cilium bgp routes advertised ipv4 unicast`.
- **Gateways** (Envoy Gateway) — [`envoy-gateway/gateway/`](../kubernetes/apps/network/envoy-gateway/gateway):
  `envoy-internal` → `10.1.81.11` (`internal.${SECRET_DOMAIN}`, LAN),
  `envoy-external` → `10.1.81.12` (`external.${SECRET_DOMAIN}`, reached via the tunnel).
  Wildcard TLS from cert-manager; apps attach with `HTTPRoute`.
- **DNS** — external-dns → Cloudflare (`cloudflare-dns`) + UniFi (`unifi-dns`).
- **Internet** — `cloudflare-tunnel` → `envoy-external` ClusterIP; no open ports.
- **Certificates** — `letsencrypt-production` (DNS-01) + `internal-ca` ClusterIssuers.
- **Encryption** — pod↔pod WireGuard between nodes; node-to-node encryption off.
