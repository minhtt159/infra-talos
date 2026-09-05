# Secrets

External Secrets Operator pulls from **Vaultwarden** at runtime. Nothing secret in
git — no SOPS, no age key.

- App: `ExternalSecret` (`secretStoreRef` → `ClusterSecretStore/bitwarden-fields`),
  Vaultwarden item UUID + field → Kubernetes `Secret`.
- Cluster-wide non-secret values (`${SECRET_DOMAIN}`, …): Vaultwarden item
  `cluster-secrets`, fanned out per namespace by a `ClusterExternalSecret`, injected via
  `postBuild.substituteFrom`.
- ESO reaches Vaultwarden through an in-cluster `bitwarden-cli` bridge. Its login is the
  one bootstrap secret ESO can't fetch itself: SOPS-encrypted in the **private** Omni repo,
  applied by a seed task ([rebuild runbook](runbooks/cluster-rebuild.md)).

Need a secret → add an `ExternalSecret`. Never commit the value.
