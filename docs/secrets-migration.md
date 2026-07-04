# SOPS → External Secrets Operator (Vaultwarden) migration

End state: **one** SOPS file remains
([`stores/secret.sops.yaml`](../kubernetes/apps/external-secrets/external-secrets/stores/secret.sops.yaml)
— the Vaultwarden credential for the bridge). Everything else comes from
Vaultwarden through ESO.

## Architecture

```
Vaultwarden ⇦ bw serve (bitwarden-cli pod) ⇦ ESO webhook ClusterSecretStores ⇦ ExternalSecret ⇨ k8s Secret
```

Three `ClusterSecretStore`s, pick by where the value lives on the Vaultwarden item:

| Store | remoteRef.key | remoteRef.property | Use for |
|---|---|---|---|
| `bitwarden-login` | item UUID | `username` / `password` | login items |
| `bitwarden-fields` | item UUID | custom field name | most k/v secrets |
| `bitwarden-notes` | item UUID | — | multiline blobs (e.g. democratic-csi driver config) |

Item UUID: `bw list items --search <name>` or the GUID in the Vaultwarden URL.

## One-time setup

1. Create a dedicated Vaultwarden account (or org collection) for the cluster.
2. Fill real values in `stores/secret.sops.yaml`, then:
   `sops --encrypt --in-place kubernetes/apps/external-secrets/external-secrets/stores/secret.sops.yaml`
3. Merge → Flux deploys ESO + bridge. Verify:
   `kubectl -n external-secrets get clustersecretstores` → all `Valid`.

## Per-secret migration loop

For each SOPS secret below: create the Vaultwarden item → add an
`ExternalSecret` next to the app (same `app/` dir, add to its
`kustomization.yaml`) → wait for the Secret to be `SecretSynced` → delete the
`*.sops.yaml` + its kustomization entry in the same commit.

`ExternalSecret` template:

```yaml
apiVersion: external-secrets.io/v1
kind: ExternalSecret
metadata:
  name: <app>
spec:
  refreshInterval: 1h
  secretStoreRef:
    kind: ClusterSecretStore
    name: bitwarden-fields
  target:
    name: <existing-secret-name>   # keep the name apps already reference
    creationPolicy: Owner
  data:
    - secretKey: <KEY_IN_SECRET>
      remoteRef:
        key: <VAULTWARDEN-ITEM-UUID>
        property: <FIELD_NAME>
```

## Inventory / checklist

- [x] `cert-manager/cert-manager/app/secret.sops.yaml` — reuses the `cloudflare-dns` item (same token, two consumers)
- [x] `network/cloudflare-dns/app/secret.sops.yaml` → `bitwarden-fields` (pilot)
- [x] `network/cloudflare-tunnel/app/secret.sops.yaml` → `bitwarden-fields` (`tunnel-token`)
- [x] `network/unifi-dns/app/secret.sops.yaml` → `bitwarden-fields` (VW field `api-token` → k8s key `api-key`)
- [x] `observability/grafana/instance/grafanasecrets.sops.yaml` → `bitwarden-login`
- [x] `democratic-csi/nfs/app/secretstruenas.sops.yaml` — full driver YAML → secure note + `bitwarden-notes`, template the whole blob:
  ```yaml
  target:
    name: truenas-nfs-secret-config
    template:
      data:
        driver-config-file.yaml: "{{ .config }}"
  data:
    - secretKey: config
      remoteRef: {key: <UUID>}
  ```
- [x] `democratic-csi/iscsi/app/secretstruenas.sops.yaml` — same pattern
- [ ] `flux-system/flux-instance/app/secret.sops.yaml` — webhook token → `bitwarden-fields` (deferred)
- [x] **cluster-secrets cutover (last):**
  1. Create Vaultwarden item `cluster-secrets` with custom field `SECRET_DOMAIN`.
  2. Put its UUID in `stores/clusterexternalsecret.yaml`, uncomment it in `stores/kustomization.yaml`.
  3. Remove `components: [../../components/sops]` from every `kubernetes/apps/*/kustomization.yaml`.
  4. Delete `kubernetes/components/sops/`.
- [ ] Shrink `.sops.yaml` to a single rule for the bridge secret; drop the stale `talos/*` rule.
- [ ] Local cleanup: age key stays (still decrypts the one bootstrap file); remove any other SOPS tooling habits.

## Rollback

Each migration commit is independently revertible: revert → SOPS secret
returns, ESO-owned Secret is pruned. The bridge itself has no consumers until
`ExternalSecret`s exist, so deploying it is risk-free.

## Known weak spots

- `bw serve` session can go stale → liveness probe forces `/sync?force=true`
  every 2 min and restarts the pod on failure. If Vaultwarden is down, existing
  k8s Secrets stay in place (ESO keeps last value).
- Vaultwarden item **UUIDs** are the contract — deleting/recreating an item
  changes its UUID and breaks the referencing `ExternalSecret`.
