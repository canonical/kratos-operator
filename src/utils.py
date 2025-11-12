# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, TypeVar

from ops import CharmBase

from constants import (
    DATABASE_INTEGRATION_NAME,
    KRATOS_EXTERNAL_IDP_INTEGRATOR_INTEGRATION_NAME,
    KRATOS_INFO_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from integrations import PublicRouteData

if TYPE_CHECKING:
    from charm import KratosCharm


def dict_to_action_output(d: Dict) -> Dict:
    """Convert all keys in a dict to the format of a juju action output.

    Recursively replaces underscores in dict keys with dashes.

    For example:
        {"a_b_c": 123} -> {"a-b-c": 123}
        {"a_b": {"c_d": "aba"}} -> {"a-b": {"c-d": "aba"}}

    """
    return {
        k.replace("_", "-"): dict_to_action_output(v) if isinstance(v, dict) else v
        for k, v in d.items()
    }


CharmEventHandler = TypeVar("CharmEventHandler", bound=Callable[..., Any])
CharmType = TypeVar("CharmType", bound=CharmBase)
Condition = Callable[[CharmType], bool]


def leader_unit(func: CharmEventHandler) -> CharmEventHandler:
    """A decorator, applied to any event hook handler, to validate juju unit leadership."""

    @wraps(func)
    def wrapper(charm: CharmBase, *args: Any, **kwargs: Any) -> Optional[Any]:
        if not charm.unit.is_leader():
            return None

        return func(charm, *args, **kwargs)

    return wrapper  # type: ignore[return-value]


def integration_existence(integration_name: str) -> Condition:
    """A factory of integration existence condition."""

    def wrapped(charm: CharmBase) -> bool:
        return bool(charm.model.relations[integration_name])

    return wrapped


peer_integration_exists = integration_existence(PEER_INTEGRATION_NAME)
database_integration_exists = integration_existence(DATABASE_INTEGRATION_NAME)
kratos_info_integration_exists = integration_existence(KRATOS_INFO_INTEGRATION_NAME)
external_idp_integrator_integration_exists = integration_existence(
    KRATOS_EXTERNAL_IDP_INTEGRATOR_INTEGRATION_NAME
)
public_route_integration_exists = integration_existence(PUBLIC_ROUTE_INTEGRATION_NAME)


def container_connectivity(charm: CharmBase) -> bool:
    return charm.unit.get_container(WORKLOAD_CONTAINER).can_connect()


def database_resource_is_created(charm: "KratosCharm") -> bool:
    return charm.database_requirer.is_resource_created()


def secrets_is_ready(charm: "KratosCharm") -> bool:
    return charm.secrets.is_ready


def migration_is_ready(charm: "KratosCharm") -> bool:
    return not charm.migration_needed


def public_route_is_ready(charm: "KratosCharm") -> bool:
    """Checks whether public route URL is required or is ready.

    A public route URL is required when the external-idp-integrator
    integration exists and it is ready when the public-route is ready.
    """
    return (
        not external_idp_integrator_integration_exists(charm)
        or PublicRouteData.load(charm.public_route).url
    )


def external_hostname_is_ready(charm: "KratosCharm") -> bool:
    """Checks whether external hostname can be required or is ready.

    An external hostname is required when either kratos-info or external-idp-integrator
    integrations exist and it is ready when public-route integration exists.
    """
    return not (
        kratos_info_integration_exists(charm) and external_idp_integrator_integration_exists(charm)
    ) or public_route_integration_exists(charm)


def passwordless_config_is_valid(charm: "KratosCharm") -> bool:
    """Checks whether passwordless login method configuration is valid.

    Passwordless login method can be enabled only when OIDC WebAuthn sequencing is not enabled.
    """
    # TODO(nsklikas): Remove this when we update Kratos version and start using the passkey config to enable
    # passkeys.
    return not (
        charm.charm_config["enable_oidc_webauthn_sequencing"]
        and charm.charm_config["enable_passwordless_login_method"]
    )


# Condition failure causes early return without doing anything
NOOP_CONDITIONS: tuple[Condition, ...] = (
    peer_integration_exists,
    database_integration_exists,
    database_resource_is_created,
    secrets_is_ready,
    migration_is_ready,
    external_hostname_is_ready,
    public_route_is_ready,
    passwordless_config_is_valid,
)

# Condition failure causes early return with corresponding event deferred
EVENT_DEFER_CONDITIONS: tuple[Condition, ...] = (container_connectivity,)
