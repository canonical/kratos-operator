# privileged-session-max-age Specification

## Purpose

Kratos has a setting for the age of a privileged session, `selfservice.flows.settings.privileged_session_max_age`. This capability says which value the charm sets and how a related charm gets that value.

Key decisions:

- **The charm sets the default of Kratos, `1h`, explicitly.** Thus `kratos-info` can publish the value that Kratos uses.
- **The leader publishes the value in `kratos-info`.** A requirer such as the login UI can then apply the same age.

Non-goals:

- An option that changes the age.
- A check that a requirer uses the published value.

## Requirements
### Requirement: The charm sets the age of a privileged session explicitly
The charm SHALL set `selfservice.flows.settings.privileged_session_max_age` to `1h` in the configuration file, wherever the charm renders the settings flow. The value is a constant of the charm. It is the same as the default of Kratos. The charm has no option for it. The setting does not depend on multitenancy.

#### Scenario: The charm renders the settings flow
- **WHEN** the login UI publishes its URLs and the charm renders the settings flow
- **THEN** the settings flow in the configuration file has `privileged_session_max_age: 1h`

### Requirement: The charm publishes the age of a privileged session
The leader SHALL publish the field `privileged_session_max_age` with the value `1h` in the application data of each `kratos-info` relation (interface `kratos_info`). The leader SHALL publish the field each time that it publishes the other fields of `kratos-info`, with multitenancy on or off. A unit that is not the leader publishes nothing.

The charm publishes the field also when it renders no settings flow. Kratos then uses its default, which is the same value.

#### Scenario: A requirer joins
- **WHEN** an application joins `kratos-info` and the charm has a public URL
- **THEN** the leader publishes `privileged_session_max_age` as `1h` with the other fields

