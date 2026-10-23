## 1. Libraries

- [x] 1.1 Update `login_ui_endpoints` to LIBPATCH 6, which adds the field `byosso_enabled`
- [x] 1.2 Update `kratos_info` to LIBPATCH 7, which adds the optional field `privileged_session_max_age`

## 2. The flag of the login UI

- [x] 2.1 Add `byosso_enabled` and the property `multitenancy` to `LoginUIEndpointData` in `src/integrations.py`
- [x] 2.2 Give `SESSION_WHOAMI_REQUIRED_AAL=aal1` from `LoginUIEndpointData.to_env_vars()` while multitenancy is on
- [x] 2.3 Pass the login UI data as the first source of the Pebble layer in `src/charm.py`
- [x] 2.4 Give `multitenancy` to the template from `LoginUIEndpointData.to_service_configs()`

## 3. The configuration template

- [x] 3.1 Enable `totp` and `lookup_secret` under multitenancy in `templates/kratos.yaml.j2`
- [x] 3.2 Render the login webhooks for `totp` and `lookup_secret` under multitenancy
- [x] 3.3 Render `login_hints: True` in the registration flow under multitenancy
- [x] 3.4 Render the hook `show_verification_ui` after an OIDC registration under multitenancy
- [x] 3.5 Render `privileged_session_max_age` in the settings flow from the constant `PRIVILEGED_SESSION_MAX_AGE`

## 4. The options that multitenancy needs

- [x] 4.1 Add `multitenancy_config_is_valid` to `src/utils.py` and to `NOOP_CONDITIONS`
- [x] 4.2 Report the blocked status in `_on_collect_status`
- [x] 4.3 Return early from `_on_kratos_info_provider_ready` while the options do not fit multitenancy
- [x] 4.4 Say in `charmcraft.yaml` how the 3 options relate to multitenancy

## 5. The age of a privileged session

- [x] 5.1 Pass `PRIVILEGED_SESSION_MAX_AGE` to `send_info_relation_data` in `src/charm.py`

## 6. Tests

- [x] 6.1 Test the rendered configuration with and without multitenancy in `tests/unit/test_configs.py`
- [x] 6.2 Test the planned environment and the blocked status in `tests/unit/test_charm.py`
- [x] 6.3 Test that a blocked charm leaves `kratos-info` as it was, and that `relation-broken` publishes it
- [x] 6.4 Test the flag in `tests/unit/test_integrations.py` and the condition in `tests/unit/test_utils.py`
