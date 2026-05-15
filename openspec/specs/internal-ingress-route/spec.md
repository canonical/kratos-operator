## ADDED Requirements

### Requirement: Internal ingress route integration
The charm SHALL provide an `internal-ingress-route` relation (interface: `istio_ingress_route`) that uses `IstioIngressRouteRequirer` to publish HTTP routing configuration to an Istio ingress provider, enabling the Kratos public and admin APIs to be reached from internal or cross-cluster networks.

#### Scenario: Relation added and provider ready
- **WHEN** an `internal-ingress-route` relation is added and the Istio ingress provider sets `external_host`
- **THEN** the charm SHALL submit an `IstioIngressRouteConfig` with HTTP listeners for both `KRATOS_PUBLIC_PORT` and `KRATOS_ADMIN_PORT`, and HTTP routes for the admin API paths (`/admin/identities`, `/admin/recovery`, `/admin/sessions`) and public API paths (`/schemas`, `/self-service`, `/sessions`)

#### Scenario: TLS enabled by provider
- **WHEN** the Istio ingress provider sets `tls_enabled` to `True`
- **THEN** the charm SHALL derive the internal endpoint scheme as `https`

#### Scenario: TLS disabled or absent
- **WHEN** the Istio ingress provider sets `tls_enabled` to `False` or does not set it
- **THEN** the charm SHALL derive the internal endpoint scheme as `http`

### Requirement: Internal endpoints derived from Istio provider data
The charm SHALL construct internal public and admin endpoint URLs from the `external_host` and `tls_enabled` provided by `IstioIngressRouteRequirer`. When no external host is available, the charm SHALL fall back to in-cluster DNS names.

#### Scenario: External host available
- **WHEN** `IstioIngressRouteRequirer.external_host` returns a non-empty string
- **THEN** the charm SHALL set both the internal public endpoint and admin endpoint to `{scheme}://{external_host}`

#### Scenario: External host not available
- **WHEN** `IstioIngressRouteRequirer.external_host` returns an empty string
- **THEN** the charm SHALL set the internal public endpoint to `http://{app}.{model}.svc.cluster.local:{KRATOS_PUBLIC_PORT}` and the admin endpoint to `http://{app}.{model}.svc.cluster.local:{KRATOS_ADMIN_PORT}`

### Requirement: Internal ingress route relation broken
When the `internal-ingress-route` relation is removed, the charm SHALL fall back to in-cluster DNS endpoints.

#### Scenario: Relation broken
- **WHEN** the `internal-ingress-route` relation is broken
- **THEN** the charm SHALL update internal endpoints to the in-cluster DNS fallback values and trigger a configuration update

### Requirement: Submit config only when leader
The charm SHALL only call `IstioIngressRouteRequirer.submit_config()` from the leader unit.

#### Scenario: Non-leader unit receives ready event
- **WHEN** a non-leader unit receives the ingress `on.ready` event
- **THEN** the charm SHALL NOT call `submit_config()` and SHALL NOT raise an error
