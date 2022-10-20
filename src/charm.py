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
from charms.data_platform_libs.v0.database_requires import DatabaseCreatedEvent, DatabaseRequires
from jinja2 import Environment, FileSystemLoader
from lightkube import Client
from lightkube.core.exceptions import ApiError
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import Layer, PathError, ProtocolError

logger = logging.getLogger(__name__)


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = "kratos"
        self.container = self.unit.get_container(self._container_name)
        self._stored.set_default(
            **{"db_username": None, "db_password": None, "db_endpoints_ip": None}
        )

        self.resource_handler = KubernetesResourceHandler(
            template_files=self._template_files,
            context=self._context,
            field_manager=self.model.app.name,
        )
        self.lightkube_client = Client(namespace=self.model.name, field_manager="lightkube")

        self.database = DatabaseRequires(
            self,
            relation_name="pg-database",
            database_name="database",
            extra_user_roles="SUPERUSER",
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.database.on.database_created, self._on_database_created)
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
            jinja_env = Environment(loader=FileSystemLoader("src"))
            template_config = jinja_env.get_template("config.yaml")
            rendered_config = template_config.render(
                dsn=f"postgres://{self._stored.db_username}:{self._stored.db_password}@{self._stored.db_endpoints_ip}/postgres",
                # TODO smtp config
                smtp_connection_uri="smtps://test:test@mailslurper:1025/?skip_ssl_verify=true",
            )
            self.container.push("/etc/config/kratos.yaml", rendered_config, make_dirs=True)
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

        if not self.container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring pebble ready event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        # check db connection
        if not self._stored.db_username:
            event.defer()
            logger.info("Missing database details. Deferring pebble ready event.")
            self.unit.status = BlockedStatus("Waiting for database creation")
            return

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

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        # Handle the created database
        # Create configuration file for app
        self.unit.status = MaintenanceStatus("Retrieving database details")

        self._stored.db_username = event.username
        self._stored.db_password = event.password
        self._stored.db_endpoints_ip = event.endpoints

        self._on_pebble_ready(event)

        self.unit.status = ActiveStatus()

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
