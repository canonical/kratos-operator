## 1. Library & Dependencies

- [x] 1.1 Verify `lib/charms/istio_ingress_k8s/v0/istio_ingress_route.py` is present (already fetched via `charmcraft fetch-lib`)
- [x] 1.2 Add `charms.istio_ingress_k8s.v0.istio_ingress_route` to `charmcraft.yaml` `charm-libs` section
- [x] 1.3 Check whether `lib/charms/traefik_k8s/` is still imported elsewhere; if not, remove the vendored library

## 2. Constants & charmcraft.yaml

- [x] 2.1 Rename `PUBLIC_ROUTE_INTEGRATION_NAME` to `PUBLIC_INGRESS_ROUTE_INTEGRATION_NAME` with value `"public-ingress-route"` in `src/constants.py`
- [x] 2.2 Rename `INTERNAL_ROUTE_INTEGRATION_NAME` to `INTERNAL_INGRESS_ROUTE_INTEGRATION_NAME` with value `"internal-ingress-route"` in `src/constants.py`
- [x] 2.3 Replace the `public-route` entry in `charmcraft.yaml` `requires` with `public-ingress-route` (interface: `istio_ingress_route`)
- [x] 2.4 Replace the `internal-route` entry in `charmcraft.yaml` `requires` with `internal-ingress-route` (interface: `istio_ingress_route`)

## 3. Integrations Layer (`src/integrations.py`)

- [x] 3.1 Replace `from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer` with imports from `charms.istio_ingress_k8s.v0.istio_ingress_route` (`IstioIngressRouteRequirer`, `IstioIngressRouteConfig`, `Listener`, `ProtocolType`, `HTTPRoute`, `HTTPRouteMatch`, `HTTPPathMatch`, `HTTPPathMatchType`, `BackendRef`)
- [x] 3.2 Update `PublicRouteData.load()`: replace `_external_host()` / `_scheme()` class methods with calls to `requirer.external_host` and `requirer.tls_enabled`; derive scheme as `"https" if requirer.tls_enabled else "http"`
- [x] 3.3 Replace the `config: dict` field on `PublicRouteData` with `config: IstioIngressRouteConfig`; build the config using typed Pydantic models (one HTTP listener on `KRATOS_PUBLIC_PORT`, routes for `/self-service`, `/schemas`, `/.well-known/webauthn.js`, `/self-service/methods/oidc/callback`)
- [x] 3.4 Update `InternalRouteData.load()` similarly: use `requirer.external_host` / `requirer.tls_enabled`; build `IstioIngressRouteConfig` with listeners for both `KRATOS_PUBLIC_PORT` and `KRATOS_ADMIN_PORT` and appropriate HTTP routes
- [x] 3.5 Replace the `config: dict` field on `InternalRouteData` with `config: IstioIngressRouteConfig`
- [x] 3.6 Remove the two Jinja2 `open("templates/...")` calls and delete `templates/public-route.j2` and `templates/internal-route.j2`
- [x] 3.7 Update all references to the renamed constants (`PUBLIC_ROUTE_INTEGRATION_NAME` → `PUBLIC_INGRESS_ROUTE_INTEGRATION_NAME`, etc.)

## 4. Charm Orchestration (`src/charm.py`)

- [x] 4.1 Replace `from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer` with `from charms.istio_ingress_k8s.v0.istio_ingress_route import IstioIngressRouteRequirer`
- [x] 4.2 In `__init__`: rename `self.public_route` to `self.public_ingress_route` and `self.internal_route` to `self.internal_ingress_route`; update `TraefikRouteRequirer(...)` to `IstioIngressRouteRequirer(self, relation_name=PUBLIC_INGRESS_ROUTE_INTEGRATION_NAME)` (no explicit relation argument needed)
- [x] 4.3 Replace event handler registrations: remove `relation_joined` / `relation_changed` / `relation_broken` subscriptions for both route relations; subscribe to `self.public_ingress_route.on.ready` → `_on_public_route_changed` and `self.internal_ingress_route.on.ready` → `_on_internal_route_changed`
- [x] 4.4 Update `_on_public_route_changed`: remove `self.public_route._relation = event.relation` workaround; call `self.public_ingress_route.is_ready()` then `self.public_ingress_route.submit_config(PublicRouteData.load(self.public_ingress_route).config)`
- [x] 4.5 Update `_on_public_route_broken`: remove `_relation` workaround; let the existing `on.ready` emission from the lib trigger `_on_public_route_changed` (broken event also fires `on.ready`); update any direct reference to `self.public_route` → `self.public_ingress_route`
- [x] 4.6 Update `_on_internal_route_changed`: same pattern as 4.4, using `self.internal_ingress_route`
- [x] 4.7 Update `_on_internal_route_broken`: same pattern as 4.5
- [x] 4.8 Update all remaining references to `self.public_route` → `self.public_ingress_route` and `self.internal_route` → `self.internal_ingress_route` throughout the file
- [x] 4.9 Update imports for renamed constants

## 5. Utilities (`src/utils.py`)

- [x] 5.1 Update `public_route_is_ready()` to reference `charm.public_ingress_route` instead of `charm.public_route`
- [x] 5.2 Update any other helpers referencing old integration names or the old requirer attribute

## 6. Tests

- [x] 6.1 Update unit tests in `tests/unit/` that reference `traefik_route`, `TraefikRouteRequirer`, `public-route`, `internal-route`, `submit_to_traefik`, or the `_relation` workaround
- [x] 6.2 Add/update State-based tests (`ops.testing`) for `on.ready` events from `IstioIngressRouteRequirer` (both route ready and route broken scenarios)
- [x] 6.3 Verify `tox -e unit` passes with no regressions

## 7. Validation

- [x] 7.1 Run `tox -e fmt` and `tox -e lint` and fix any issues
- [x] 7.2 Confirm `templates/public-route.j2` and `templates/internal-route.j2` have been deleted
- [x] 7.3 Confirm no remaining imports from `charms.traefik_k8s.v0.traefik_route` in `src/`
- [x] 7.4 Confirm `charmcraft.yaml` no longer contains `traefik_route` interface entries
