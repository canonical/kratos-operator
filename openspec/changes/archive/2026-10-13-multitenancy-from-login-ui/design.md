## Context

The charm renders the configuration file of Kratos from its options and from the data of its relations. The options `enforce_mfa`, `enable_local_idp` and `enable_oidc_webauthn_sequencing` decide 2 things:

- The session level (AAL) that Kratos needs at `whoami` (`SESSION_WHOAMI_REQUIRED_AAL`).
- If the methods `totp` and `lookup_secret` are on.

When the login UI runs Bring Your Own SSO, the login UI decides when a sign-in needs MFA. Kratos must then accept a session that did not complete a second factor. Kratos must also keep the second-factor methods available. The login UI uses 2 more functions of Kratos: the account linking and the verification of email addresses.

The charm of the login UI publishes its URLs in the `ui-endpoint-info` relation. The charm publishes its endpoints and some of its options in the `kratos-info` relation.

## Goals / Non-Goals

**Goals:**

- Apply all the settings that multitenancy needs together, from one flag.
- Keep the rendered configuration the same as before while the flag is off, but for one line.
- Keep Kratos and `kratos-info` in agreement while the options do not fit multitenancy.
- Publish the age of a privileged session, so that a requirer can apply the same age.

**Non-Goals:**

- A session level for each caller of Kratos.
- An option for the age of a privileged session.
- A check of `enable_local_idp` for multitenancy.

## Decisions

### Decision 1: The flag of the login UI turns multitenancy on

**Chosen**: The charm reads `byosso_enabled` from `ui-endpoint-info`. Multitenancy is on only while the value is the text `true`. The charm has no option for multitenancy.

**Rationale**: The settings are of use only in one combination, so one flag sets all of them. The charm of the login UI publishes `true` in `ui-endpoint-info` when it plans its workload with Bring Your Own SSO.

**Alternative considered**: One option for each setting of Kratos: the session level, the login hints, and the verification after an OIDC registration. We turned it down because only one combination of the 3 options is of use.

### Decision 2: The session level is `aal1` and the second-factor methods stay enabled

**Chosen**: With multitenancy the charm sets `SESSION_WHOAMI_REQUIRED_AAL` to `aal1`. It enables `totp` and `lookup_secret` for all values of `enforce_mfa` and `enable_local_idp`. Thus the option `enforce_mfa` has no effect on Kratos.

**Rationale**: The login UI decides when a sign-in needs MFA. Thus Kratos must accept a session that did not complete a second factor at `whoami`. TOTP and recovery codes (the method `lookup_secret`) must stay available.

The login UI data is the first source of the Pebble layer. Thus its value for the variable replaces the value that the options give.

### Decision 3: The login hints and the verification after an OIDC registration

**Chosen**: With multitenancy the charm sets `selfservice.flows.registration.login_hints` to `True`. It also adds the hook `show_verification_ui` after a registration through an OIDC provider.

**Rationale**: Kratos stops a registration when an account already has the email address. Kratos then lists the ways in which that account can sign in. The account linking of Kratos needs that list. The hook shows the verification page for an address that the identity provider did not confirm.

### Decision 4: The charm blocks on options that do not fit

**Chosen**: With multitenancy the charm needs `enable_verification=True` and `enable_oidc_webauthn_sequencing=False`. With other values the charm blocks and does not change the options.

**Rationale**: With multitenancy the login UI decides when a sign-in needs MFA. OIDC-WebAuthn sequencing also decides that. The login UI relies on Kratos to verify the addresses that an external identity provider did not confirm.

Each description of the 3 options in `charmcraft.yaml` names the option of the login UI, `byosso_enabled`. The word multitenancy alone is not enough there. The charm of the login UI also uses that word for the tenants that it reads from the Tenant Service.

### Decision 5: A blocked charm leaves `kratos-info` as it was

**Chosen**: While multitenancy is on and the options do not fit it, the charm plans nothing. The leader publishes nothing to `kratos-info` in that time.

**Rationale**: A blocked charm does not change Kratos. `kratos-info` carries options of the charm: `mfa_enabled`, `verification_enabled` and `oidc_webauthn_sequencing_enabled`. The data must agree with the Kratos that runs.

**Alternative considered**: Publish `kratos-info` from the new options while the charm is blocked. We turned it down because the related charms then get a configuration that Kratos does not run.

### Decision 6: The change adds no observer for the removal of the relation with the login UI

**Chosen**: The charm already observes `relation-broken` of `ui-endpoint-info` with the handler of `relation-changed`. The change relies on that observer.

**Rationale**: The removal of the relation turns multitenancy off, and that clears a block. The handler then plans the services from the options. The leader publishes `kratos-info` in the same hook.

### Decision 7: The age of a privileged session is explicit and published

**Chosen**: The charm sets `selfservice.flows.settings.privileged_session_max_age` to the constant `1h`. The leader publishes the same constant in `kratos-info`.

**Rationale**: `1h` is the default of Kratos. The charm sets it explicitly so that `kratos-info` can publish the value that Kratos uses. The login UI can then apply the same age.

## Risks / Trade-offs

- **The session level applies to all callers.** `SESSION_WHOAMI_REQUIRED_AAL` is one value for the whole of Kratos. With multitenancy, a caller other than the login UI also gets an answer for a session with one factor. A deployment must not rely on Kratos to enforce the second factor for such a caller.
- **A new requirer gets no data while the charm is blocked.** The leader publishes nothing to `kratos-info` in that time. This is also true for a new relation. The requirer gets its data when the block clears.
- **A new container while the charm is blocked.** The charm does not start Kratos in a workload container that starts in that time. Such a container starts, for example, after a pod restart or a refresh of the charm.
- **Other work waits while the charm is blocked.** The charm stops before it submits the routes and pushes the CA bundle. It also stops before it updates the redirect URIs of the providers. This is the same for the other preconditions of the charm.
- **The charm does not check `enable_local_idp`.** The charm renders the `verification` flow and the `code` method only when `enable_local_idp` is on. With `enable_local_idp=False` and multitenancy, the charm renders the hook `show_verification_ui` without them.
- **The methods follow the options again when multitenancy goes off.** The charm then enables `totp` and `lookup_secret` only as the options say. The charm does not look at the second factors that users set up while multitenancy was on.
