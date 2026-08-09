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

## Layout

```
applicationsets/bank0.yaml   the shape: one Application per env config file
envs/bank0/<env>.yaml        per-environment values; adding an env is adding a file
projects/bank0.yaml          AppProject scoping bank0 to its two namespaces
```

Kargo promotes `staging → production` by rewriting `chartVersion` in
`envs/bank0/production.yaml` — which is why these files live in a directory Flux
will never fight over.

Note the failure mode of a git file generator: if its glob matches nothing it
reports success and produces zero Applications. An environment that silently
stops existing looks exactly like one that was never added.
