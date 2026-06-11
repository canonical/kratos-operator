## ADDED Requirements

### Requirement: Public ingress route integration
The charm SHALL provide a `public-ingress-route` relation (interface: `istio_ingress_route`) that uses `IstioIngressRouteRequirer` to publish HTTP routing configuration to an Istio ingress provider, enabling the Kratos public API to be reached from the public internet.

#### Scenario: Relation added and provider ready
- **WHEN** a `public-ingress-route` relation is added and the Istio ingress provider sets `external_host`
- **THEN** the charm SHALL submit an `IstioIngressRouteConfig` with a single HTTP listener on `KRATOS_PUBLIC_PORT` and HTTP routes covering the Kratos public API paths (`/self-service`, `/schemas`, `/.well-known/webauthn.js`, `/self-service/methods/oidc/callback`)

#### Scenario: TLS enabled by provider
- **WHEN** the Istio ingress provider sets `tls_enabled` to `True`
- **THEN** the charm SHALL derive the public URL scheme as `https`

#### Scenario: TLS disabled by provider
- **WHEN** the Istio ingress provider sets `tls_enabled` to `False` or does not set it
- **THEN** the charm SHALL derive the public URL scheme as `http`

### Requirement: Public URL derived from Istio provider data
The charm SHALL construct the Kratos public base URL from the `external_host` and `tls_enabled` values provided by the Istio ingress provider via `IstioIngressRouteRequirer.external_host` and `IstioIngressRouteRequirer.tls_enabled`.

#### Scenario: External host available
- **WHEN** `IstioIngressRouteRequirer.external_host` returns a non-empty string
- **THEN** the charm SHALL set `SERVE_PUBLIC_BASE_URL` to `{scheme}://{external_host}` and `SELFSERVICE_ALLOWED_RETURN_URLS` accordingly

#### Scenario: External host not yet set
- **WHEN** `IstioIngressRouteRequirer.external_host` returns an empty string
- **THEN** the charm SHALL NOT set `SERVE_PUBLIC_BASE_URL` and SHALL report `WaitingStatus`

### Requirement: Public ingress route relation broken
When the `public-ingress-route` relation is removed, the charm SHALL clear the public URL and trigger a configuration update.

#### Scenario: Relation broken
- **WHEN** the `public-ingress-route` relation is broken
- **THEN** the charm SHALL update its configuration with no public URL set and SHALL reconfigure the Kratos workload

### Requirement: Public ingress route readiness gate
The charm SHALL block workload configuration when the `public-ingress-route` is required but not yet ready.

#### Scenario: External IdP integration present, no public ingress route
- **WHEN** the `kratos-external-idp` integration exists AND the `public-ingress-route` relation has no ready provider
- **THEN** the charm SHALL report `WaitingStatus("Waiting for public ingress")`
