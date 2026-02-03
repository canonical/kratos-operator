# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from contextlib import contextmanager
from typing import Callable, Iterator

import jubilant
import yaml
from integration.constants import KRATOS_APP
from tenacity import retry, stop_after_attempt, wait_exponential

StatusPredicate = Callable[[jubilant.Status], bool]

logger = logging.getLogger(__name__)


def juju_model_factory(model_name: str) -> jubilant.Juju:
    juju = jubilant.Juju()
    try:
        juju.add_model(model_name, config={"logging-config": "<root>=INFO"})
    except jubilant.CLIError as e:
        if "already exists" not in e.stderr:
            raise

    juju.model = model_name

    return juju


def get_unit_data(model: jubilant.Juju, unit_name: str) -> dict:
    """Get the data for a given unit."""
    stdout = model.cli("show-unit", unit_name)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


def get_integration_data(
    juju: jubilant.Juju, app_name: str, integration_name: str, unit_num: int = 0
) -> dict | None:
    """Get the integration data for a given integration."""
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


def get_app_integration_data(
    juju: jubilant.Juju,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> dict | None:
    """Get the application data for a given integration."""
    data = get_integration_data(juju, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


def get_unit_address(juju: jubilant.Juju, app_name: str, unit_num: int = 0) -> str:
    """Get the address of a given unit."""
    data = get_unit_data(juju, f"{app_name}/{unit_num}")
    return data["address"]


@contextmanager
def remove_integration(
    juju: jubilant.Juju, remote_app_name: str, integration_name: str
) -> Iterator[None]:
    """Temporarily remove an integration from the application.

    Integration is restored after the context is exited.
    """

    @retry(
        wait=wait_exponential(multiplier=2, min=1, max=30),
        stop=stop_after_attempt(10),
        reraise=True,
    )
    def _reintegrate() -> None:
        juju.integrate(f"{KRATOS_APP}:{integration_name}", remote_app_name)

    juju.remove_relation(f"{KRATOS_APP}:{integration_name}", remote_app_name)
    try:
        yield
    finally:
        _reintegrate()


def all_active(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_active(status, *apps)


def all_blocked(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_blocked(status, *apps)


def all_waiting(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.all_waiting(status, *apps)


def any_error(*apps: str) -> StatusPredicate:
    return lambda status: jubilant.any_error(status, *apps)


def is_active(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_active


def is_blocked(app: str) -> StatusPredicate:
    return lambda status: status.apps[app].is_blocked


def unit_number(app: str, expected_num: int) -> StatusPredicate:
    return lambda status: len(status.apps[app].units) == expected_num


def and_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: all(predicate(status) for predicate in predicates)


def or_(*predicates: StatusPredicate) -> StatusPredicate:
    return lambda status: any(predicate(status) for predicate in predicates)
