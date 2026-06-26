## 1. Library & Dependencies

- [x] 1.1 Verify `lib/charms/istio_ingress_k8s/v0/istio_ingress_route.py` is present (already fetched via `charmcraft fetch-lib`)
- [x] 1.2 Add `charms.istio_ingress_k8s.v0.istio_ingress_route` to `charmcraft.yaml` `charm-libs` section
- [x] 1.3 Check whether `lib/charms/traefik_k8s/` is still imported elsewhere; if not, remove the vendored library
- [x] 1.4 Replace vendored `lib/charms/istio_ingress_k8s/` with `charmlibs-interfaces-istio-ingress-route==1.0.2` from PyPI in `requirements.txt`; update all imports from `charms.istio_ingress_k8s.v0.istio_ingress_route` to `charmlibs.interfaces.istio_ingress_route`

## 2. Constants & charmcraft.yaml

- [x] 2.1 Keep `PUBLIC_ROUTE_INTEGRATION_NAME = "public-route"` in `src/constants.py`
- [x] 2.2 Keep `INTERNAL_ROUTE_INTEGRATION_NAME = "internal-route"` in `src/constants.py`
- [x] 2.3 Replace the `public-route` entry in `charmcraft.yaml` `requires` with `public-route` (interface: `istio_ingress_route`)
- [x] 2.4 Replace the `internal-route` entry in `charmcraft.yaml` `requires` with `internal-route` (interface: `istio_ingress_route`)
- [x] 2.5 Add `INGRESS_HTTP_PORT = 80` and `INGRESS_HTTPS_PORT = 443` to `src/constants.py`

## 3. Integrations Layer (`src/integrations.py`)

- [x] 3.1 Replace `from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer` with imports from `charmlibs.interfaces.istio_ingress_route` (`IstioIngressRouteRequirer`, `IstioIngressRouteConfig`, `Listener`, `ProtocolType`, `HTTPRoute`, `HTTPRouteMatch`, `HTTPPathMatch`, `HTTPPathMatchType`, `BackendRef`)
- [x] 3.2 Update `PublicRouteData.load()`: replace `_external_host()` / `_scheme()` class methods with calls to `requirer.external_host` and `requirer.tls_enabled`; derive scheme as `"https" if requirer.tls_enabled else "http"`
- [x] 3.3 Replace the `config: dict` field on `PublicRouteData` with `config: IstioIngressRouteConfig`; build the config using typed Pydantic models: listener on `INGRESS_HTTPS_PORT` or `INGRESS_HTTP_PORT` based on `tls_enabled`; a `"public-api"` HTTPRoute with multiple path-prefix matches (`/self-service`, `/schemas`, `/sessions`) and a `"webauthn-js"` HTTPRoute with exact match and URL rewrite filter
- [x] 3.4 Update `InternalRouteData.load()` similarly: use `requirer.external_host` / `requirer.tls_enabled`; build `IstioIngressRouteConfig` with a single listener on `INGRESS_HTTPS_PORT` or `INGRESS_HTTP_PORT`, an `"admin-api"` HTTPRoute for admin paths and a `"public-api"` HTTPRoute for public paths
- [x] 3.5 Replace the `config: dict` field on `InternalRouteData` with `config: IstioIngressRouteConfig`
- [x] 3.6 Remove the two Jinja2 `open("templates/...")` calls and delete `templates/public-route.j2` and `templates/internal-route.j2`
- [x] 3.7 Keep constant names `PUBLIC_ROUTE_INTEGRATION_NAME` and `INTERNAL_ROUTE_INTEGRATION_NAME`; update all references

## 4. Charm Orchestration (`src/charm.py`)

- [x] 4.1 Replace `from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer` with `from charmlibs.interfaces.istio_ingress_route import IstioIngressRouteRequirer`
- [x] 4.2 In `__init__`: keep `self.public_route` and `self.internal_route` attributes; update `TraefikRouteRequirer(...)` to `IstioIngressRouteRequirer(self, relation_name=PUBLIC_ROUTE_INTEGRATION_NAME)`
- [x] 4.3 Replace event handler registrations: subscribe to `self.public_route.on.ready` → `_on_public_route_changed` and `self.internal_route.on.ready` → `_on_internal_route_changed`
- [x] 4.4 Move `submit_config` calls for both public and internal routes into `_holistic_handler`: call `submit_config` only when `self.unit.is_leader()` and `<requirer>.is_ready()` return `True`
- [x] 4.5 Simplify `_on_public_route_changed` and `_on_internal_route_changed` to only set unit status and delegate to `_holistic_handler`
- [x] 4.6 All references use `self.public_route` and `self.internal_route` throughout the file
- [x] 4.7 Update imports for renamed constants

## 5. Utilities (`src/utils.py`)

- [x] 5.1 `public_route_is_ready()` references `charm.public_route`
- [x] 5.2 `public_route_integration_exists` uses `PUBLIC_ROUTE_INTEGRATION_NAME`

## 6. Tests

- [x] 6.1 Update unit tests in `tests/unit/` that reference `traefik_route`, `TraefikRouteRequirer`, `submit_to_traefik`, or the `_relation` workaround
- [x] 6.2 Add/update State-based tests (`ops.testing`) for `on.ready` events from `IstioIngressRouteRequirer` (both route ready and route broken scenarios)
- [x] 6.3 Update `test_when_event_emitted` tests for route-changed events to provide full state (peer, database, secret, mocked migration) so the holistic handler proceeds to call `submit_config`
- [x] 6.4 Update integration tests: deploy login-ui from `istio/edge` channel; integrate `istio-ingress-k8s` with `istio-k8s` for both public and internal apps; add `login-ui:public-route` → `istio-public:istio-ingress-route` integration
- [x] 6.5 Verify `tox -e unit` passes with no regressions

## 7. Validation

- [x] 7.1 Run `tox -e fmt` and `tox -e lint` and fix any issues
- [x] 7.2 Confirm `templates/public-route.j2` and `templates/internal-route.j2` have been deleted
- [x] 7.3 Confirm no remaining imports from `charms.traefik_k8s.v0.traefik_route` in `src/`
- [x] 7.4 Confirm `charmcraft.yaml` no longer contains `traefik_route` interface entries
