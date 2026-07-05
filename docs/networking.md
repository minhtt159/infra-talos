# Networking & ingress

- **LoadBalancer IPs** — Cilium LB IPAM, pool `10.1.80.0/24`, announced over
  L2 on `ens*`/`eth*` interfaces
  ([`cilium/app/networks.yaml`](../kubernetes/apps/kube-system/cilium/app/networks.yaml)).
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
