#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Kratos."""

import glob
import logging
from pathlib import Path

from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from charmed_kubeflow_chisme.kubernetes import KubernetesResourceHandler
from charmed_kubeflow_chisme.lightkube.batch import delete_many
from charmed_kubeflow_chisme.pebble import update_layer
from lightkube import Client
from lightkube.core.exceptions import ApiError
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer, PathError, ProtocolError

logger = logging.getLogger(__name__)


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = "kratos"
        self.container = self.unit.get_container(self._container_name)

        self.resource_handler = KubernetesResourceHandler(
            template_files=self._template_files,
            context=self._context,
            field_manager=self.model.app.name,
        )
        self.lightkube_client = Client(namespace=self.model.name, field_manager="lightkube")

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.remove, self._on_remove)

    @property
    def _template_files(self):
        src_dir = Path("src/manifests")
        manifests = list(glob.glob(f"{src_dir}/*.yaml"))
        return manifests

    @property
    def _context(self):
        context = {
            "app_name": self.model.app.name,
        }
        return context

    @property
    def _pebble_layer(self) -> Layer:
        pebble_layer = {
            "summary": "kratos layer",
            "description": "pebble config layer for kratos",
            "services": {
                self._container_name: {
                    "override": "replace",
                    "summary": "Kratos Operator layer",
                    "startup": "enabled",
                    "command": "kratos serve all --config /etc/config/kratos.yaml",
                    "environment": {
                        "DSN": "postgres://username:password@10.152.183.152:5432/postgres",
                        "COURIER_SMTP_CONNECTION_URI": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true",
                    },
                }
            },
            "checks": {
                "ready": {
                    "override": "replace",
                    "http": {"url": "http://localhost:4434/admin/health/ready"},
                },
                "alive": {
                    "override": "replace",
                    "http": {"url": "http://localhost:4434/admin/health/ready"},
                },
            },
        }
        return Layer(pebble_layer)

    def _update_kratos_config(self) -> None:
        """Push configs and identity schema into kratos container."""
        try:
            with open("src/config.yaml", encoding="utf-8") as config_file:
                config = config_file.read()
                self.container.push("/etc/config/kratos.yaml", config, make_dirs=True)
            with open("src/identity.default.schema.json", encoding="utf-8") as schema_file:
                schema = schema_file.read()
                self.container.push("/etc/config/identity.default.schema.json", schema)
            logger.info("Pushed configs to kratos container")
        except (ProtocolError, PathError) as e:
            logger.error(str(e))
            self.unit.status = BlockedStatus(str(e))

    def _on_install(self, _) -> None:
        """Event Handler for install event.

        - push configs
        - apply service manifests
        - update pod template to expose 2 ports
        """
        self.unit.status = MaintenanceStatus("Configuring/deploying resources")

        if self.container.can_connect():
            self._update_kratos_config()

        try:
            self.resource_handler.apply()

        except (ApiError, ErrorWithStatus) as e:
            if isinstance(e, ApiError):
                logger.error(
                    f"Applying resources failed with ApiError status code {e.status.code}, error response: {e.response}"
                )
                self.unit.status = BlockedStatus(f"ApiError: {e.status.code}")
            else:
                logger.info(e.msg)
                self.unit.status = e.status
        else:
            self.unit.status = ActiveStatus()

    def _on_pebble_ready(self, event) -> None:
        """Event Handler for pebble ready event.

        Do the following if kratos container can be connected:
        - push configs
        - update pebble layer.
        """
        self.unit.status = MaintenanceStatus("Configuring/deploying resources")

        if self.container.can_connect():
            self._update_kratos_config()
            try:
                update_layer(self._container_name, self.container, self._pebble_layer, logger)
                self.unit.status = ActiveStatus()
            except ErrorWithStatus as e:
                self.model.unit.status = e.status
                if isinstance(e.status, BlockedStatus):
                    logger.error(str(e.msg))
                else:
                    logger.info(str(e.msg))
        else:
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring pebble ready event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")

    def _on_remove(self, _) -> None:
        """Event Handler for pebble ready event.

        Remove additional kubernetes resources
        """
        manifests = self.resource_handler.render_manifests(force_recompute=False)
        try:
            delete_many(self.lightkube_client, manifests)
        except ApiError as e:
            logger.warning(str(e))


if __name__ == "__main__":
    main(KratosCharm)
