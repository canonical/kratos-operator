# multitenancy Specification

## Purpose

The login UI can run Bring Your Own SSO. With it, a tenant registers its own identity provider, and the members of the tenant sign in through that provider. Kratos then needs a group of settings, which the charm calls multitenancy. This capability says when the charm applies these settings and what they are. It also says what the charm does when its options do not fit them.

Key decisions:

- **The flag of the login UI turns multitenancy on.** The charm has no option for it. The settings are of use only in one combination, so one flag sets all of them.
- **The login UI decides when a sign-in needs MFA.** Thus Kratos must accept a session that did not complete a second factor at `whoami`. TOTP and recovery codes (the method `lookup_secret`) must stay available for all values of `enforce_mfa` and `enable_local_idp`.
- **The login hints are for the account linking of Kratos.** Kratos stops a registration when an account already has the email address. Kratos then lists the ways in which that account can sign in.
- **Kratos verifies an address that an identity provider did not confirm.** For that purpose the hook `show_verification_ui` runs after a registration through an OIDC provider.
- **The charm blocks on options that do not fit, and does not change them.** OIDC-WebAuthn sequencing also decides when a sign-in needs MFA. The login UI relies on the verification of addresses by Kratos.
- **A blocked charm plans nothing and leaves `kratos-info` as it was.** A Kratos that runs keeps its configuration. The related charms must not get a configuration that Kratos does not run.
- **The removal of the `ui-endpoint-info` relation clears a block in the same hook.** The charm handles `relation-broken` of that relation as it handles `relation-changed`. It does so with or without multitenancy.

Non-goals:

- A session level (AAL) for each caller. `SESSION_WHOAMI_REQUIRED_AAL` is one value for the whole of Kratos. Thus every caller of Kratos gets `aal1`, not only the login UI.
- The decision when a sign-in needs MFA. The login UI makes it.
- A check of `enable_local_idp`. The charm renders the `verification` flow and the `code` method only when `enable_local_idp` is on, with or without multitenancy.
- TOTP and recovery codes that stay enabled after multitenancy goes off. The options decide the methods again.
- Kratos in a workload container that starts while the charm is blocked. The charm does not start Kratos in that container until the block clears.

## Requirements
### Requirement: The flag of the login UI turns multitenancy on
The charm SHALL read the field `byosso_enabled` from the application data of the `ui-endpoint-info` relation (interface `login_ui_endpoints`). Multitenancy SHALL be on only while the value of the field is the text `true`. In each of these cases multitenancy is off:

- The field has another value, for example `false` or an empty text.
- The field is absent.
- There is no `ui-endpoint-info` relation.
- The charm cannot read the data of the relation.

The charm has no option that turns multitenancy on or off. The charm relies on the charm of the login UI to publish `true` only while that charm plans its workload with Bring Your Own SSO. The value does not prove that the login UI runs.

The charm SHALL apply a change of the flag in the hook that brings the change. For that purpose the charm handles `relation-broken` of `ui-endpoint-info` in the same way as `relation-changed`.

#### Scenario: The login UI turns the flag on
- **WHEN** Kratos runs and the charm of the login UI publishes `byosso_enabled` as `true`
- **AND** the options of the charm fit multitenancy
- **THEN** the charm applies the settings for multitenancy in the `relation-changed` hook

#### Scenario: The operator removes the relation with the login UI
- **WHEN** the flag is `true` and the operator removes the `ui-endpoint-info` relation
- **THEN** multitenancy is off in the `relation-broken` hook
- **AND** the charm plans the services from its options in that hook

### Requirement: The settings of Kratos under multitenancy
While multitenancy is on and the options fit it, the charm SHALL apply all of these settings together:

| where | setting | value |
|---|---|---|
| the environment of the services `kratos` and `courier` | `SESSION_WHOAMI_REQUIRED_AAL` | `aal1` |
| the configuration file | `selfservice.methods.totp` | `enabled: True`, with `config.issuer: Identity Platform` |
| the configuration file | `selfservice.methods.lookup_secret` | `enabled: True` |
| the configuration file | `selfservice.flows.registration.login_hints` | `True` |
| the configuration file | `selfservice.flows.registration.after.oidc.hooks` | the hook `show_verification_ui`, after the webhooks and before the hook `session` |
| the configuration file | `selfservice.flows.login.after.totp.hooks` and `selfservice.flows.login.after.lookup_secret.hooks` | the login webhooks that apply to all methods or to that method |

The configuration file is `/etc/config/kratos/kratos.yaml` in the workload container.

The charm SHALL set `SESSION_WHOAMI_REQUIRED_AAL` to `aal1` also when the options ask for `highest_available`. The charm SHALL enable the methods `totp` and `lookup_secret` for all values of `enforce_mfa` and `enable_local_idp`.

The charm adds the settings of the flows only where it renders that part of the flow. The conditions for those parts do not change:

- The charm renders the registration flow, and thus `login_hints`, when there is a registration webhook or an OIDC provider. It also renders them when `enable_local_idp` is on and the login UI publishes its URLs.
- The charm renders the hooks after an OIDC registration only when there is a registration webhook or an OIDC provider.
- The charm renders the hooks after a login with a method only when a login webhook of the mode `after` applies to that method.

Because the charm enables the 2 methods, the `feature_flags` that the leader publishes in `kratos-info` contain `totp` and `backup_codes`. In `feature_flags`, `backup_codes` stands for the method `lookup_secret`.

#### Scenario: The options enforce MFA
- **WHEN** multitenancy is on, and `enforce_mfa` and `enable_local_idp` are on
- **THEN** the planned services `kratos` and `courier` have `SESSION_WHOAMI_REQUIRED_AAL` set to `aal1`

#### Scenario: The options do not enforce MFA
- **WHEN** multitenancy is on and `enforce_mfa` is off
- **THEN** the configuration file enables the methods `totp` and `lookup_secret`

#### Scenario: The registration flow with a registration webhook
- **WHEN** multitenancy is on and there is a registration webhook
- **THEN** the registration flow has `login_hints: True`
- **AND** the hooks after an OIDC registration are in this order: the webhook, `show_verification_ui`, `session`

### Requirement: The settings of Kratos without multitenancy
While multitenancy is off, the charm SHALL NOT apply the settings for multitenancy. In that time the flag SHALL NOT change these settings. The options decide them, as this table shows:

| setting | value without multitenancy |
|---|---|
| `SESSION_WHOAMI_REQUIRED_AAL` | `highest_available` when `enable_oidc_webauthn_sequencing` is on, or when `enable_local_idp` and `enforce_mfa` are on. In other cases the charm does not set the variable |
| `selfservice.methods.totp` | enabled only when `enforce_mfa` and `enable_local_idp` are on and the login UI publishes a login URL |
| `selfservice.methods.lookup_secret` | enabled only when `enable_oidc_webauthn_sequencing` is on, or when `enforce_mfa` and `enable_local_idp` are on |
| `selfservice.flows.registration.login_hints` | absent |
| the hook `show_verification_ui` after an OIDC registration | absent |
| the login webhooks under `selfservice.flows.login.after.totp.hooks` | rendered only when `enforce_mfa` and `enable_local_idp` are on |
| the login webhooks under `selfservice.flows.login.after.lookup_secret.hooks` | rendered only when `enable_oidc_webauthn_sequencing` is on, or when `enforce_mfa` and `enable_local_idp` are on |

The charm SHALL NOT block on the options that multitenancy needs while multitenancy is off.

#### Scenario: The same options with the flag off
- **WHEN** multitenancy is off, and `enforce_mfa` and `enable_oidc_webauthn_sequencing` are off
- **AND** there is a registration webhook
- **THEN** the configuration file does not enable the methods `totp` and `lookup_secret`
- **AND** the registration flow has no `login_hints`
- **AND** the hooks after an OIDC registration are in this order: the webhook, `session`

### Requirement: Multitenancy ignores the option that enforces MFA
While multitenancy is on, the option `enforce_mfa` SHALL NOT change the configuration file or the environment of the services. The login UI then decides when a sign-in needs MFA. The leader SHALL continue to publish the value of the option as `mfa_enabled` in `kratos-info`.

#### Scenario: The operator changes the option
- **WHEN** multitenancy is on and the operator changes `enforce_mfa`
- **THEN** the configuration file and the environment of the services stay the same
- **AND** `mfa_enabled` in `kratos-info` has the new value of the option

### Requirement: The options that multitenancy needs
While multitenancy is on, the charm SHALL accept only this combination of options: `enable_verification=True` and `enable_oidc_webauthn_sequencing=False`. With any other combination, each unit SHALL report a blocked status with this message:

```
Multitenancy requires `enable_verification=True` and `enable_oidc_webauthn_sequencing=False`
```

The reasons for the 2 options are these:

- With multitenancy the login UI decides when a sign-in needs MFA. OIDC-WebAuthn sequencing also decides that.
- The login UI relies on Kratos to verify the email addresses that an external identity provider did not confirm.

The charm does not change the options. In `charmcraft.yaml`, the descriptions of `enforce_mfa`, `enable_verification` and `enable_oidc_webauthn_sequencing` say how each option relates to multitenancy.

The charm adds this status after the statuses of its earlier checks. A blocked status of an earlier check shows first. The earlier checks that block are these:

- The `pg-database` relation is absent.
- The charm needs an external hostname and the `public-route` relation is absent.
- `enable_passwordless_login_method` and `enable_oidc_webauthn_sequencing` are both on.

#### Scenario: Verification is off
- **WHEN** multitenancy is on and `enable_verification` is `False`
- **THEN** the unit status is blocked with the message of this requirement

#### Scenario: Sequencing is on
- **WHEN** multitenancy is on and `enable_oidc_webauthn_sequencing` is `True`
- **THEN** the unit status is blocked with the message of this requirement

### Requirement: A charm blocked on multitenancy plans nothing
While multitenancy is on and the options do not fit it, the charm SHALL NOT plan the services and SHALL NOT write the configuration file. A Kratos that runs continues to run with the configuration that it had. The leader SHALL NOT publish to `kratos-info` in that time. Thus the requirers of `kratos-info` keep the data that agrees with the Kratos that runs.

In a workload container that starts while the charm is blocked, the charm adds no layer and writes no configuration file. Kratos does not run in that container until the block clears.

The charm stops at the same point as for its other preconditions. Thus this work also waits until the block clears:

- The submission of the route configurations.
- The update of the redirect URIs for the providers of `kratos-external-idp`.
- The push of the CA bundle and of the email templates.

The charm SHALL do this work, and the leader SHALL publish `kratos-info`, in the hook that clears the block. That hook is one of these:

- `config-changed`, when the operator corrects the options.
- `relation-changed` of `ui-endpoint-info`, when the login UI turns the flag off.
- `relation-broken` of `ui-endpoint-info`.

The charm does this work only when its other preconditions pass and it can connect to the workload container. The leader publishes `kratos-info` only when the charm has a public URL.

#### Scenario: The operator turns verification off while multitenancy is on
- **WHEN** Kratos runs with multitenancy and the operator sets `enable_verification` to `False`
- **THEN** the charm blocks and Kratos continues to run with its configuration
- **AND** `verification_enabled` in `kratos-info` stays `True`

#### Scenario: A new container while the charm is blocked
- **WHEN** Pebble becomes ready in a new workload container while the options do not fit multitenancy
- **THEN** the charm adds no layer and writes no configuration file in that container
- **AND** Kratos does not run in that container until the block clears

#### Scenario: A new requirer while the charm is blocked
- **WHEN** an application joins `kratos-info` while the options do not fit multitenancy
- **THEN** the leader publishes nothing to the new relation until the block clears

#### Scenario: The operator corrects the options
- **WHEN** the charm is blocked and the operator sets the options that multitenancy needs
- **THEN** the charm plans the services in the `config-changed` hook
- **AND** the leader publishes `kratos-info` in the same hook

#### Scenario: The operator removes the relation with the login UI while the charm is blocked
- **WHEN** the charm is blocked and the operator removes the `ui-endpoint-info` relation
- **THEN** the block clears in the `relation-broken` hook
- **AND** the charm plans the services from its options
- **AND** the leader publishes `kratos-info` in the same hook

