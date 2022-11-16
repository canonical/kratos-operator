#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Kratos."""

import glob
import logging
from pathlib import Path

import yaml
from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from charmed_kubeflow_chisme.kubernetes import KubernetesResourceHandler
from charmed_kubeflow_chisme.lightkube.batch import delete_many
from charms.data_platform_libs.v0.database_requires import DatabaseCreatedEvent, DatabaseRequires
from lightkube import Client
from lightkube.core.exceptions import ApiError
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ChangeError, ExecError, Layer, PathError, ProtocolError

logger = logging.getLogger(__name__)


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = "kratos"
        self._container = self.unit.get_container(self._container_name)
        self._config_file_path = "/etc/config/kratos.yaml"
        self._identity_schema_file_path = "/etc/config/identity.default.schema.json"

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
        self.framework.observe(self.on.update_status, self._on_pebble_ready)
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
                    "http": {"url": "http://localhost:4434/admin/health/alive"},
                },
            },
        }
        return Layer(pebble_layer)

    @property
    def _config(self) -> str:
        db_info = self._get_database_relation_info()
        config = {
            "log": {"level": "trace"},
            "identity": {
                "default_schema_id": "default",
                "schemas": [{"id": "default", "url": f"file://{self._identity_schema_file_path}"}],
            },
            "selfservice": {
                "default_browser_return_url": "http://127.0.0.1:9999/",
                "flows": {
                    "registration": {
                        "enabled": True,
                        "ui_url": "http://127.0.0.1:9999/registration",
                    }
                },
            },
            "dsn": f"postgres://{db_info['username']}:{db_info['password']}@{db_info['endpoints']}/postgres",
            "courier": {
                "smtp": {
                    # TODO: dynamic connection uri through charm config
                    "connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"
                }
            },
        }

        return yaml.dump(config)

    def _update_layer(self) -> None:
        """Updates the Pebble configuration layer if changed."""
        # Get current layer
        current_layer = self._container.get_plan()
        # Create a new config layer
        new_layer = self._pebble_layer

        if current_layer.services != new_layer.services:
            self.unit.status = MaintenanceStatus("Applying new pebble layer")
            self._container.add_layer(self._container_name, new_layer, combine=True)
            logger.info("Pebble plan updated with new configuration, replanning")
            try:
                self._container.replan()
            except ChangeError as err:
                logger.error(str(err))
                self.unit.status = BlockedStatus("Failed to replan")
                return

        # Get current config
        current_config = self._container.pull(self._config_file_path).read()
        if current_config != self._config:
            self._container.push(self._config_file_path, self._config, make_dirs=True)
            logger.info("Updated kratos config")

        self._container.restart(self._container_name)

    def _get_database_relation_info(self) -> dict:
        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data["username"],
            "password": relation_data["password"],
            "endpoints": relation_data["endpoints"],
        }

    def _set_default_identity_schema(self) -> None:
        """Push configs and identity schema into kratos container."""
        try:
            with open("src/identity.default.schema.json", encoding="utf-8") as schema_file:
                schema = schema_file.read()
                self._container.push(self._identity_schema_file_path, schema)
            logger.info("Pushed configs to kratos container")
        except (ProtocolError, PathError) as e:
            logger.error(str(e))
            self.unit.status = BlockedStatus(str(e))

    def _update_container(self, event) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring pebble ready event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        if not self.model.relations["pg-database"]:
            event.defer()
            logger.error("Missing required relation with postgresql")
            self.model.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self.database.is_database_created():
            event.defer()
            logger.info("Missing database details. Deferring pebble ready event.")
            self.unit.status = BlockedStatus("Waiting for database creation")
            return

        self._set_default_identity_schema()

        try:
            self._update_layer()
            self.unit.status = ActiveStatus()
        except ErrorWithStatus as e:
            self.model.unit.status = e.status
            if isinstance(e.status, BlockedStatus):
                logger.error(str(e.msg))
            else:
                logger.info(str(e.msg))

        self._run_sql_migration()

    def _run_sql_migration(self) -> None:
        """Runs a command to create SQL schemas and apply migration plans."""
        process = self._container.exec(
            ["kratos", "migrate", "sql", "-e", "--config", self._config_file_path, "--yes"],
            timeout=20.0,
        )
        try:
            stdout, _ = process.wait_output()
            logger.info(f"Executing automigration: {stdout}")
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            self.unit.status = BlockedStatus("Database migration job failed")

    def _on_install(self, event) -> None:
        """Event Handler for install event.

        - push configs
        - apply service manifests
        - update pod template to expose 2 ports
        """
        self.unit.status = MaintenanceStatus("Configuring/deploying resources")

        if not self.unit.is_leader():
            event.defer()
            logger.info("Waiting for leadership to apply k8s resources")
            self.unit.status = WaitingStatus("Waiting for leadership to apply k8s resources")
            return

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
        self._update_container(event)
        self.unit.status = ActiveStatus()

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        self.unit.status = MaintenanceStatus("Retrieving database details")
        self._update_container(event)
        self.unit.status = ActiveStatus()

    def _on_remove(self, _) -> None:
        """Event Handler for remove event.

        Remove additional kubernetes resources
        """
        manifests = self.resource_handler.render_manifests(force_recompute=False)
        try:
            delete_many(self.lightkube_client, manifests)
        except ApiError as e:
            logger.warning(str(e))


if __name__ == "__main__":
    main(KratosCharm)
