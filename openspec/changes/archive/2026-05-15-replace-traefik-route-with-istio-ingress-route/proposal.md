## Why

The charm currently uses two `traefik_route` integrations (`public-route` and `internal-route`) to expose the Kratos workload through Traefik. The platform is migrating to Istio as the service mesh and ingress controller, requiring these integrations to be replaced with an `istio-ingress-route` interface that communicates routing rules via Istio's VirtualService/Gateway model rather than Traefik's dynamic configuration format.

## What Changes

- Remove the `public-route` relation (interface: `traefik_route`) from `charmcraft.yaml`
- Remove the `internal-route` relation (interface: `traefik_route`) from `charmcraft.yaml`
- Add new `public-ingress-route` relation (interface: `istio_ingress_route`) to `charmcraft.yaml`
- Add new `internal-ingress-route` relation (interface: `istio_ingress_route`) to `charmcraft.yaml`
- Replace `TraefikRouteRequirer` (from `charms.traefik_k8s.v0.traefik_route`) with the Istio ingress route requirer library in `src/integrations.py`
- Replace Traefik-specific Jinja2 route templates (`templates/public-route.j2`, `templates/internal-route.j2`) with Istio-compatible routing configuration
- Update `PublicRouteData` and `InternalRouteData` in `src/integrations.py` to use the new library and data model
- Update `src/charm.py` event handlers, requirer setup, and `submit_to_traefik` calls to use the new Istio API
- Update constants (`PUBLIC_ROUTE_INTEGRATION_NAME`, `INTERNAL_ROUTE_INTEGRATION_NAME`) to reflect new relation names
- **BREAKING**: `public-route` and `internal-route` relation names change; existing deployments must migrate to the new relations

## Capabilities

### New Capabilities

- `public-ingress-route`: Exposes the Kratos public API to the internet via an Istio-based ingress integration, providing the external URL for OAuth callbacks, self-service flows, and schema endpoints.
- `internal-ingress-route`: Exposes the Kratos public and admin APIs for cross-cluster or internal-network traffic via an Istio-based ingress integration, providing internal endpoints for admin operations.

### Modified Capabilities

<!-- No existing specs in openspec/specs/ - no requirement-level changes to existing capabilities. -->

## Impact

- `src/charm.py`: Event handler registration, `TraefikRouteRequirer` instantiation, `submit_to_traefik` calls, and `_on_*_route_*` handlers
- `src/integrations.py`: `PublicRouteData.load()`, `InternalRouteData.load()`, import of `TraefikRouteRequirer`
- `src/utils.py`: `public_route_is_ready()` and any helpers referencing the old requirer
- `src/constants.py`: `PUBLIC_ROUTE_INTEGRATION_NAME`, `INTERNAL_ROUTE_INTEGRATION_NAME`
- `charmcraft.yaml`: `requires` section (relation names and interfaces)
- `templates/public-route.j2`, `templates/internal-route.j2`: Replaced or removed (Istio config format differs from Traefik)
- `lib/charms/traefik_k8s/`: The vendored `traefik_route` lib may be removed if no longer used by any other integration
- `tests/unit/`: Any tests that mock or reference `TraefikRouteRequirer`, route submission, or the old relation names
