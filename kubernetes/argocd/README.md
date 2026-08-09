# kubernetes/argocd/

Argo CD's territory. **Flux does not read this directory.**

That is worth stating loudly, because the path now *looks* like Flux's. It isn't:
Flux reads exactly two paths in this repo —

| path | what reads it |
| --- | --- |
| `kubernetes/flux/cluster` | the FluxInstance's own sync spec |
| `kubernetes/apps` | the `cluster-apps` Kustomization |

`kubernetes/argocd` is a sibling of `kubernetes/apps`, not a child. Move it inside
`kubernetes/apps` and both controllers would claim the same objects.

The split, per environment:

| owner | objects |
| --- | --- |
| Flux (`kubernetes/apps/bank0-*`) | namespace, DB role + database, DSN + JWT Secrets, HTTPRoutes, TLS |
| Argo CD (here) | the bank0 Helm release — Deployments, Services, migration Job |

Bootstrapping is app-of-apps: Flux seeds a single root `Application`
(`kubernetes/apps/argocd/argocd/app/root-application.yaml`) that points back at
this directory and recurses. Everything else is Argo CD's to sync.

Kargo promotes `staging → production` by committing to `apps/bank0-production.yaml`
here — which is why app manifests live in a directory Flux will never fight over.
