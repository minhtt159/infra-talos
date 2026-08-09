# argocd/

Argo CD's territory. **Flux does not read this directory** — its `cluster-apps`
Kustomization is pinned to `./kubernetes/apps`, so nothing here is reconciled by
Flux and the two controllers never contend for the same object.

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
