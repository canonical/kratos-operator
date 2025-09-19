# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar

from ops import CharmBase

from constants import (
    DATABASE_INTEGRATION_NAME,
    KRATOS_EXTERNAL_IDP_INTEGRATOR_INTEGRATION_NAME,
    KRATOS_INFO_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_INGRESS_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)


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
Condition = Callable[[CharmBase], bool]


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
public_ingress_integration_exists = integration_existence(PUBLIC_INGRESS_INTEGRATION_NAME)


def container_connectivity(charm: CharmBase) -> bool:
    return charm.unit.get_container(WORKLOAD_CONTAINER).can_connect()
