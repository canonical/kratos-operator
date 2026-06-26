## ADDED Requirements

### Requirement: Public ingress route integration
The charm SHALL provide a `public-route` relation (interface: `istio_ingress_route`) that uses `IstioIngressRouteRequirer` from `charmlibs-interfaces-istio-ingress-route` (installed via PyPI) to publish HTTP routing configuration to an Istio ingress provider, enabling the Kratos public API to be reached from the public internet.

#### Scenario: Relation added and provider ready
- **WHEN** a `public-route` relation is added and the Istio ingress provider sets `external_host`
- **THEN** the charm SHALL submit an `IstioIngressRouteConfig` with:
  - A single HTTP listener on port `INGRESS_HTTPS_PORT` (443) if `tls_enabled` is `True`, or `INGRESS_HTTP_PORT` (80) otherwise
  - A `"public-api"` HTTPRoute with a single backend on `KRATOS_PUBLIC_PORT` (4433) and path-prefix matches for `/self-service`, `/schemas`, and `/sessions`
  - A `"webauthn-js"` HTTPRoute with an exact match on `/.well-known/webauthn.js` and a URL rewrite filter replacing the path with `/.well-known/ory/webauthn.js`

#### Scenario: TLS enabled by provider — listener port
- **WHEN** the Istio ingress provider sets `tls_enabled` to `True`
- **THEN** the charm SHALL use port `443` (`INGRESS_HTTPS_PORT`) for the ingress listener and derive the public URL scheme as `https`

#### Scenario: TLS disabled by provider — listener port
- **WHEN** the Istio ingress provider sets `tls_enabled` to `False` or does not set it
- **THEN** the charm SHALL use port `80` (`INGRESS_HTTP_PORT`) for the ingress listener and derive the public URL scheme as `http`

### Requirement: Public URL derived from Istio provider data
The charm SHALL construct the Kratos public base URL from the `external_host` and `tls_enabled` values provided by the Istio ingress provider via `IstioIngressRouteRequirer.external_host` and `IstioIngressRouteRequirer.tls_enabled`.

#### Scenario: External host available
- **WHEN** `IstioIngressRouteRequirer.external_host` returns a non-empty string
- **THEN** the charm SHALL set `SERVE_PUBLIC_BASE_URL` to `{scheme}://{external_host}` and `SELFSERVICE_ALLOWED_RETURN_URLS` accordingly

#### Scenario: External host not yet set
- **WHEN** `IstioIngressRouteRequirer.external_host` returns an empty string
- **THEN** the charm SHALL NOT set `SERVE_PUBLIC_BASE_URL` and SHALL report `WaitingStatus`

### Requirement: Route config submitted from the holistic handler
The charm SHALL call `IstioIngressRouteRequirer.submit_config()` from within `_holistic_handler`, not directly in the route-changed event handler.

#### Scenario: Leader unit, relation ready, all conditions met
- **WHEN** the leader unit executes `_holistic_handler` and `public_route.is_ready()` returns `True`
- **THEN** the charm SHALL call `submit_config` with the built `IstioIngressRouteConfig`

#### Scenario: Non-leader unit
- **WHEN** a non-leader unit processes any event
- **THEN** the charm SHALL NOT call `submit_config()`

### Requirement: Public ingress route relation broken
When the `public-route` relation is removed, the charm SHALL clear the public URL and trigger a configuration update.

#### Scenario: Relation broken
- **WHEN** the `public-route` relation is broken
- **THEN** the charm SHALL update its configuration with no public URL set and SHALL reconfigure the Kratos workload

### Requirement: Public ingress route readiness gate
The charm SHALL block workload configuration when the `public-route` is required but not yet ready.

#### Scenario: External IdP integration present, no public ingress route
- **WHEN** the `kratos-external-idp` integration exists AND the `public-route` relation has no ready provider
- **THEN** the charm SHALL report `WaitingStatus("Waiting for public ingress")`
