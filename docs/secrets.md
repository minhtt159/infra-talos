# Secrets (External Secrets Operator)

Secrets are pulled at runtime from **Vaultwarden** by the **External Secrets
Operator** (ESO) — nothing secret is committed to this repo (no SOPS, no age key).

- Each app declares an `ExternalSecret` (`secretStoreRef` →
  `ClusterSecretStore/bitwarden-fields`) mapping a Vaultwarden item's fields into a
  Kubernetes `Secret`.
- Non-secret, cluster-wide values (e.g. `${SECRET_DOMAIN}`) live in the
  `cluster-secrets` Vaultwarden item, fanned out to every namespace by a
  `ClusterExternalSecret` and injected via `postBuild.substituteFrom`.
- ESO reaches Vaultwarden through an in-cluster `bitwarden-cli` bridge. Its login
  is the one **bootstrap** secret that can't come from ESO itself — seeded
  out-of-band (SOPS-encrypted in the **private** Omni repo, applied by a seed task;
  see the [rebuild runbook](runbooks/cluster-rebuild.md)) and **not** stored here.

> If a workload needs a secret, add an `ExternalSecret` — never commit the value
> (encrypted or not).
