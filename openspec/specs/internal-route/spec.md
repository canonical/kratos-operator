## ADDED Requirements

### Requirement: Internal ingress route integration
The charm SHALL provide an `internal-route` relation (interface: `istio_ingress_route`) that uses `IstioIngressRouteRequirer` from `charmlibs-interfaces-istio-ingress-route` (installed via PyPI) to publish HTTP routing configuration to an Istio ingress provider, enabling the Kratos public and admin APIs to be reached from internal or cross-cluster networks.

#### Scenario: Relation added and provider ready
- **WHEN** an `internal-route` relation is added and the Istio ingress provider sets `external_host`
- **THEN** the charm SHALL submit an `IstioIngressRouteConfig` with:
  - A single HTTP listener on port `INGRESS_HTTPS_PORT` (443) if `tls_enabled` is `True`, or `INGRESS_HTTP_PORT` (80) otherwise
  - An `"admin-api"` HTTPRoute with a backend on `KRATOS_ADMIN_PORT` (4434) and path-prefix matches for `/admin/identities`, `/admin/recovery`, and `/admin/sessions`
  - A `"public-api"` HTTPRoute with a backend on `KRATOS_PUBLIC_PORT` (4433) and path-prefix matches for `/schemas`, `/self-service`, and `/sessions`

#### Scenario: TLS enabled by provider — listener port
- **WHEN** the Istio ingress provider sets `tls_enabled` to `True`
- **THEN** the charm SHALL use port `443` (`INGRESS_HTTPS_PORT`) for the ingress listener and derive the internal endpoint scheme as `https`

#### Scenario: TLS disabled or absent — listener port
- **WHEN** the Istio ingress provider sets `tls_enabled` to `False` or does not set it
- **THEN** the charm SHALL use port `80` (`INGRESS_HTTP_PORT`) for the ingress listener and derive the internal endpoint scheme as `http`

### Requirement: Internal endpoints derived from Istio provider data
The charm SHALL construct internal public and admin endpoint URLs from the `external_host` and `tls_enabled` provided by `IstioIngressRouteRequirer`. When no external host is available, the charm SHALL fall back to in-cluster DNS names.

#### Scenario: External host available
- **WHEN** `IstioIngressRouteRequirer.external_host` returns a non-empty string
- **THEN** the charm SHALL set both the internal public endpoint and admin endpoint to `{scheme}://{external_host}`

#### Scenario: External host not available
- **WHEN** `IstioIngressRouteRequirer.external_host` returns an empty string
- **THEN** the charm SHALL set the internal public endpoint to `http://{app}.{model}.svc.cluster.local:{KRATOS_PUBLIC_PORT}` and the admin endpoint to `http://{app}.{model}.svc.cluster.local:{KRATOS_ADMIN_PORT}`

### Requirement: Route config submitted from the holistic handler
The charm SHALL call `IstioIngressRouteRequirer.submit_config()` for the internal route from within `_holistic_handler`, not directly in the route-changed event handler.

#### Scenario: Leader unit, relation ready, all conditions met
- **WHEN** the leader unit executes `_holistic_handler` and `internal_route.is_ready()` returns `True`
- **THEN** the charm SHALL call `submit_config` with the built `IstioIngressRouteConfig`

#### Scenario: Non-leader unit
- **WHEN** a non-leader unit processes any event
- **THEN** the charm SHALL NOT call `submit_config()`

### Requirement: Internal ingress route relation broken
When the `internal-route` relation is removed, the charm SHALL fall back to in-cluster DNS endpoints.

#### Scenario: Relation broken
- **WHEN** the `internal-route` relation is broken
- **THEN** the charm SHALL update internal endpoints to the in-cluster DNS fallback values and trigger a configuration update
