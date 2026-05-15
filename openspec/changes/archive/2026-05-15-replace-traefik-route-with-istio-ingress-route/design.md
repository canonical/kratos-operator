## Context

The Kratos operator currently integrates with Traefik as its ingress controller using two `traefik_route` relations:

- **`public-route`**: exposes the Kratos public API to the internet (self-service flows, OIDC callbacks, schema endpoints).
- **`internal-route`**: exposes both public and admin APIs for cross-cluster or internal network traffic.

Both are implemented via `TraefikRouteRequirer` from `charms.traefik_k8s.v0.traefik_route`. The requirer submits raw Traefik dynamic JSON configuration (routers, middlewares, services) rendered from Jinja2 templates (`templates/public-route.j2`, `templates/internal-route.j2`). The provider side responds with `external_host` and `scheme`, from which the charm derives full URLs for Kratos configuration.

The platform is moving to Istio as the service mesh and ingress controller. The `istio-ingress-route` interface exposes services via Istio VirtualService/Gateway objects rather than Traefik's HTTP dynamic config.

## Goals / Non-Goals

**Goals:**
- Replace both `traefik_route` relations with `istio_ingress_route` relations in `charmcraft.yaml`
- Replace `TraefikRouteRequirer` with the Istio ingress route requirer library in `src/integrations.py` and `src/charm.py`
- Preserve the same functional outcomes: a fully-qualified external URL for public traffic and internal endpoint URLs for admin/public traffic
- Remove Traefik-specific route templates and replace with Istio-compatible route submission (or remove if the Istio lib handles routing internally)
- Update all event handlers, constants, and unit tests accordingly
- Remove the vendored `traefik_route` library if it is no longer referenced by any other integration

**Non-Goals:**
- Changing Kratos's network port assignments (`KRATOS_PUBLIC_PORT`, `KRATOS_ADMIN_PORT`)
- Adding new routing rules or path prefixes beyond what the current Traefik config exposes
- Supporting a dual-stack transition period (both Traefik and Istio simultaneously)
- Changes to the PostgreSQL, SMTP, OIDC, or any non-ingress integrations

## Decisions

### Decision 1: Replace both relations atomically (vs. incremental migration)

**Chosen**: Replace both `internal-route` and `public-route` in a single change.

**Rationale**: The two relations share identical structural patterns (requirer instantiation, event handling, data loading). A single atomic change avoids a half-migrated state that would require testing with both Traefik and Istio libraries simultaneously, increasing complexity with no benefit.

**Alternative considered**: Migrate `public-route` first, then `internal-route`. Rejected because the charm's `public_route_is_ready` guard and `InternalRouteData` referencing the public URL mean the two are functionally coupled.

---

### Decision 2: Relation naming — use `public-ingress-route` and `internal-ingress-route`

**Chosen**: New relation names `public-ingress-route` (interface: `istio_ingress_route`) and `internal-ingress-route` (interface: `istio_ingress_route`).

**Rationale**: The new names remove the Traefik-specific "route" suffix ambiguity and align with the Istio library's canonical naming convention. The old names (`public-route`, `internal-route`) are a **BREAKING** change regardless of naming, so clarity is preferred over continuity.

**Alternative considered**: Reuse `public-route` and `internal-route` names with the new interface. Rejected because the interface change is breaking anyway, and keeping the same names with a different interface would confuse operators.

---

### Decision 3: Data extraction from Istio lib mirrors Traefik pattern

**Chosen**: `PublicRouteData.load()` and `InternalRouteData.load()` in `src/integrations.py` are updated to use `IstioIngressRouteRequirer.external_host` (property) and `IstioIngressRouteRequirer.tls_enabled` (boolean property replacing the old `scheme` string). The dataclass shape (`url`, `config`) is preserved.

`scheme` is now derived as `"https" if requirer.tls_enabled else "http"` rather than read directly from the relation databag.

**Rationale**: The charm's consuming code (Kratos config env vars, `to_env_vars()`, `to_service_configs()`) depends on the `URL` objects produced by these classes. Keeping the same output contract means zero changes needed upstream in `src/charm.py` beyond event handler wiring and requirer type swaps.

**Alternative considered**: Refactor the data classes entirely to reflect an Istio-native model. Deferred — the refactor can happen in a follow-up change once the library API is stable.

---

### Decision 4: Replace Traefik Jinja2 templates with typed Istio config objects

**Chosen**: Delete `templates/public-route.j2` and `templates/internal-route.j2`. Replace with typed `IstioIngressRouteConfig` objects built directly in Python using the library's Pydantic models (`Listener`, `HTTPRoute`, `HTTPRouteMatch`, `BackendRef`).

**Rationale**: The Istio lib uses structured Pydantic models (not a raw JSON dict), so Jinja2 rendering is no longer needed. The `submit_config(IstioIngressRouteConfig)` method accepts a typed object, removing the json-render-then-parse cycle. The `config: dict` field on `PublicRouteData` and `InternalRouteData` is replaced by `config: IstioIngressRouteConfig`.

---

### Decision 5: Vendored `traefik_k8s` library removal

**Chosen**: Remove `lib/charms/traefik_k8s/` only if no other integration in the charm still imports from it.

**Rationale**: The `v2` subdirectory of the vendored lib suggests there may be other consumers. Removal must be validated by a `grep` for remaining imports before deleting.

## Risks / Trade-offs

- **[Breaking change for existing deployments]** → Document migration path in release notes; operators must remove old relations and add new ones. Juju will report `relation broken` on `public-route`/`internal-route` during upgrade.

- **[Istio library API unknown at design time]** → The exact method names (equivalent of `is_ready()`, `external_host`, `scheme`, `submit_to_*`) depend on the specific Istio requirer library. At implementation time, inspect `lib/charms/<istio_lib>/` for the actual API surface. The design assumes a structurally similar API to `TraefikRouteRequirer`.

- **[Unit tests reference TraefikRouteRequirer internals]** → Some tests mock `_relation` directly (a known bug workaround for missing `relation_joined` events). The Istio lib fires `on.ready` for both `relation_changed` and `relation_broken`, eliminating this pattern. Tests must be updated to use the new event model.

- **[`public_route_is_ready` utility]** → This function directly calls `PublicRouteData.load(charm.public_route)`. The attribute name on the charm will change from `public_route` to `public_ingress_route`; `src/utils.py` must be updated in lockstep.

## Migration Plan

1. **Pre-upgrade**: No action required on the operator side before upgrade.
2. **Upgrade**: Deploy the new charm version. The charm will report `WaitingStatus` until the new `public-ingress-route` relation is added.
3. **Post-upgrade**:
   - Remove the old `public-route` and `internal-route` relations: `juju remove-relation kratos traefik-k8s`
   - Add new relations: `juju integrate kratos istio-ingress`
4. **Rollback**: Re-deploy the previous charm version and re-add the old traefik relations.

## Open Questions

All questions resolved:

- **Istio library**: `charms.istio_ingress_k8s.v0.istio_ingress_route` — fetched and API confirmed.
- **Route config submission**: Explicit — use `IstioIngressRouteRequirer.submit_config(IstioIngressRouteConfig)`.
- **TLS / `receive-ca-cert`**: Keep the `receive-ca-cert` relation; TLS is still used.
