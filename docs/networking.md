# Networking & ingress

- **LoadBalancer IPs** — Cilium LB IPAM pool `bgp`, routed VIP prefix
  `10.1.81.0/24` **outside** the node subnet
  ([`cilium/app/networks.yaml`](../kubernetes/apps/kube-system/cilium/app/networks.yaml)).
  Services opt in with the label `announce: bgp` (Envoy gateways: EnvoyProxy
  `envoyService.labels`); each VIP is advertised as a /32 over **eBGP to the
  UniFi gateway** only from nodes that hold a local endpoint
  ([`cilium/app/bgp.yaml`](../kubernetes/apps/kube-system/cilium/app/bgp.yaml)),
  so `externalTrafficPolicy: Local` never blackholes. No UniFi network object for
  the prefix — it exists only as BGP routes on the router. L2 announcements
  retired Sept 2026 (leader election ignored pod placement, cilium/cilium#27800).
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

- **Enabling BGP on a running cluster** (done once, 2026-09-05): cilium-operator
  registers the BGP CRDs only after `bgpControlPlane.enabled` reaches it, and the
  CRs share a Flux Kustomization with the HelmRelease, so the dry-run fails until
  the CRDs exist. Apply them by hand from `cilium/cilium` at the chart version
  (`pkg/k8s/apis/cilium.io/client/crds/v2/ciliumbgp*.yaml`). Fresh bootstraps
  don't hit this — helmfile installs cilium with BGP on before Flux runs.
- **Gateways** (Envoy Gateway, Gateway API) —
  [`envoy-gateway/gateway/`](../kubernetes/apps/network/envoy-gateway/gateway):
  - `envoy-internal` → `10.1.81.11`, host `internal.${SECRET_DOMAIN}`
  - `envoy-external` → `10.1.81.12`, host `external.${SECRET_DOMAIN}`
  - both terminate TLS with the `${SECRET_DOMAIN}-production-tls` wildcard cert.
    Apps attach via `HTTPRoute` (see each app's `httproute.yaml`).
- **DNS** — `external-dns` publishes gateway hostnames to **Cloudflare**
  (`cloudflare-dns`) and **UniFi** (`unifi-dns`).
- **External access** — `cloudflare-tunnel` (cloudflared) exposes selected
  services without opening ports.
- **Certificates** — cert-manager `letsencrypt-production` ClusterIssuer
  (DNS-01 over 1.1.1.1) plus an `internal-ca` issuer.
