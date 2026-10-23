## Why

The login UI can run Bring Your Own SSO. With it, a tenant registers its own identity provider and the members of the tenant sign in through that provider. The login UI then decides when a sign-in needs MFA. It also uses the account linking of Kratos and the verification of email addresses by Kratos. Kratos needs a group of settings for that, and the settings are of use only together. The charm calls this group multitenancy.

The login UI also needs the age of a privileged session that Kratos uses. The charm did not publish that age.

## What Changes

- The charm reads the field `byosso_enabled` of the `ui-endpoint-info` relation (library `login_ui_endpoints`, LIBPATCH 6). Multitenancy is on while the value is `true`. There is no new option.
- While multitenancy is on, the charm sets these settings together:
  - `SESSION_WHOAMI_REQUIRED_AAL` is `aal1` in the environment of the services.
  - The methods `totp` and `lookup_secret` are on, for all values of `enforce_mfa` and `enable_local_idp`.
  - `selfservice.flows.registration.login_hints` is `True`.
  - The hook `show_verification_ui` runs after a registration through an OIDC provider.
- While multitenancy is on, the charm needs `enable_verification=True` and `enable_oidc_webauthn_sequencing=False`. With other values the charm blocks. A blocked charm plans nothing and leaves `kratos-info` as it was.
- While multitenancy is on, the charm ignores the option `enforce_mfa`.
- The removal of the `ui-endpoint-info` relation turns multitenancy off in the `relation-broken` hook. The charm already handles that event in the same way as `relation-changed`, so the change adds no observer.
- In `charmcraft.yaml`, the descriptions of the 3 options say how each option relates to multitenancy.
- The charm sets `selfservice.flows.settings.privileged_session_max_age` explicitly, to the default of Kratos (`1h`). The leader publishes the value as `privileged_session_max_age` in `kratos-info` (library `kratos_info`, LIBPATCH 7).

While multitenancy is off, the rendered configuration is the same as before, but for the line `privileged_session_max_age`.

## Capabilities

### New Capabilities

- `multitenancy`: when the charm configures Kratos for multitenancy, which settings it applies, which options it needs, and what a blocked charm leaves as it was.
- `privileged-session-max-age`: the age of a privileged session that the charm sets in Kratos and publishes in `kratos-info`.

### Modified Capabilities

None.

## Impact

- `src/integrations.py`: `LoginUIEndpointData` reads the flag and gives the environment variable and the template variable.
- `src/utils.py`: the condition `multitenancy_config_is_valid`, added to `NOOP_CONDITIONS`.
- `src/charm.py`: the blocked status and the early return of the `kratos-info` handler. Also the login UI data as the first source of the Pebble layer.
- `src/configs.py`, `src/constants.py`: the constant `PRIVILEGED_SESSION_MAX_AGE`.
- `templates/kratos.yaml.j2`: the conditions for multitenancy and the line `privileged_session_max_age`.
- `charmcraft.yaml`: the descriptions of `enforce_mfa`, `enable_verification` and `enable_oidc_webauthn_sequencing`.
- `lib/charms/identity_platform_login_ui_operator/v0/login_ui_endpoints.py`: the field `byosso_enabled`.
- `lib/charms/kratos/v0/kratos_info.py`: the optional field `privileged_session_max_age`.
- `tests/unit/`: tests for the rendered configuration, the planned environment, the blocked status and `kratos-info`.
- Requirers of `kratos-info` get one more field. A requirer that does not read the field sees no change.
- With multitenancy on, every caller of Kratos gets the session level (AAL) `aal1`, not only the login UI.
