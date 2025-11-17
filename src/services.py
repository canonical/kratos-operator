# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from collections import ChainMap
from typing import Optional

from ops import Container, ModelError, Unit
from ops.pebble import CheckStatus, Layer, LayerDict, ServiceInfo

from cli import CommandLine
from configs import ConfigFile
from constants import (
    CA_BUNDLE_PATH,
    CONFIG_FILE_PATH,
    KRATOS_ADMIN_PORT,
    KRATOS_PUBLIC_PORT,
    PEBBLE_READY_CHECK_NAME,
    WORKLOAD_CONTAINER,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError

logger = logging.getLogger(__name__)

PEBBLE_LAYER_DICT = {
    "summary": "pebble layer",
    "description": "pebble layer for kratos",
    "services": {
        WORKLOAD_SERVICE: {
            "override": "replace",
            "summary": "entrypoint of the kratos image",
            "command": f"kratos serve all --config {CONFIG_FILE_PATH}",
            "startup": "disabled",
        }
    },
    "checks": {
        PEBBLE_READY_CHECK_NAME: {
            "override": "replace",
            "level": "ready",
            "http": {"url": f"http://localhost:{KRATOS_ADMIN_PORT}/admin/health/ready"},
        },
        "alive": {
            "override": "replace",
            "level": "alive",
            "http": {"url": f"http://localhost:{KRATOS_ADMIN_PORT}/admin/health/alive"},
        },
    },
}


class WorkloadService:
    """Workload service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._version = ""

        self._unit: Unit = unit
        self._container: Container = unit.get_container(WORKLOAD_CONTAINER)
        self._cli = CommandLine(self._container)

    @property
    def version(self) -> str:
        self._version = self._cli.get_service_version() or ""
        return self._version

    @version.setter
    def version(self, version: str) -> None:
        if not version:
            return

        try:
            self._unit.set_workload_version(version)
        except Exception as e:
            logger.error("Failed to set workload version: %s", e)
            return

        self._version = version

    def get_service(self) -> Optional[ServiceInfo]:
        try:
            return self._container.get_service(WORKLOAD_SERVICE)
        except (ModelError, ConnectionError) as e:
            logger.error("Failed to get pebble service: %s", e)

    def is_running(self) -> bool:
        """Checks whether the service is running."""
        if not (service := self.get_service()):
            return False

        if not service.is_running():
            return False

        c = self._container.get_checks().get(PEBBLE_READY_CHECK_NAME)
        return c.status == CheckStatus.UP

    def is_failing(self) -> bool:
        """Checks whether the service has crashed."""
        if not self.get_service():
            return False

        if not (c := self._container.get_checks().get(PEBBLE_READY_CHECK_NAME)):
            return False

        return c.failures > 0

    def open_ports(self) -> None:
        self._unit.open_port(protocol="tcp", port=KRATOS_PUBLIC_PORT)
        self._unit.open_port(protocol="tcp", port=KRATOS_ADMIN_PORT)

    def push_ca_certs(self, ca_certs: str) -> None:
        self._container.push(CA_BUNDLE_PATH, ca_certs, make_dirs=True)


class PebbleService:
    """Pebble service abstraction running in a Juju unit."""

    def __init__(self, unit: Unit) -> None:
        self._unit = unit
        self._container = unit.get_container(WORKLOAD_CONTAINER)
        self._layer_dict: LayerDict = PEBBLE_LAYER_DICT

    def plan(self, layer: Layer, config_file: ConfigFile) -> None:
        self._container.add_layer(WORKLOAD_SERVICE, layer, combine=True)

        current_config_file = ConfigFile.from_workload_container(self._container)
        try:
            if config_file != current_config_file:
                self._container.push(CONFIG_FILE_PATH, config_file.content, make_dirs=True)
                self._container.restart(WORKLOAD_SERVICE)
            else:
                self._container.replan()
        except Exception as e:
            raise PebbleServiceError(f"Pebble failed to restart the workload service. Error: {e}")

    def stop(self) -> None:
        try:
            self._container.stop(WORKLOAD_SERVICE)
        except Exception as e:
            raise PebbleServiceError(f"Pebble failed to stop the workload service. Error: {e}")

    def render_pebble_layer(self, *env_var_sources: EnvVarConvertible) -> Layer:
        updated_env_vars = ChainMap(*(source.to_env_vars() for source in env_var_sources))  # type: ignore
        env_vars = {
            **DEFAULT_CONTAINER_ENV,
            **updated_env_vars,
        }
        self._layer_dict["services"][WORKLOAD_SERVICE]["environment"] = env_vars

        return Layer(self._layer_dict)
