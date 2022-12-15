#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Kratos."""

import logging

import yaml
from charms.data_platform_libs.v0.database_requires import DatabaseCreatedEvent, DatabaseRequires
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import ExecError, Layer

logger = logging.getLogger(__name__)


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = "kratos"
        self._container = self.unit.get_container(self._container_name)
        self._config_file_path = "/etc/config/kratos.yaml"
        self._identity_schema_file_path = "/etc/config/identity.default.schema.json"

        self.service_patcher = KubernetesServicePatch(self, [("admin", 4434), ("public", 4433)])

        self.database = DatabaseRequires(
            self,
            relation_name="pg-database",
            database_name="database",
            extra_user_roles="SUPERUSER",
        )

        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)

    @property
    def _pebble_layer(self) -> Layer:
        pebble_layer = {
            "summary": "kratos layer",
            "description": "pebble config layer for kratos",
            "services": {
                self._container_name: {
                    "override": "replace",
                    "summary": "Kratos Operator layer",
                    "startup": "disabled",
                    "command": f"kratos serve all --config {self._config_file_path}",
                }
            },
            "checks": {
                "kratos-ready": {
                    "override": "replace",
                    "http": {"url": "http://localhost:4434/admin/health/ready"},
                },
                "kratos-alive": {
                    "override": "replace",
                    "http": {"url": "http://localhost:4434/admin/health/alive"},
                },
            },
        }
        return Layer(pebble_layer)

    @property
    def _config(self) -> str:
        try:
            db_info = self._get_database_relation_info() or {}
        except IndexError:
            db_info = {}
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
            "dsn": f"postgres://{db_info.get('username')}:{db_info.get('password')}@{db_info.get('endpoints')}/postgres",
            "courier": {
                "smtp": {
                    # TODO: dynamic connection uri through charm config
                    "connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"
                }
            },
        }

        return yaml.dump(config)

    def _get_database_relation_info(self) -> dict:
        """Get database info from relation data bag."""
        relation_id = self.database.relations[0].id
        print(
            f"DEBUGGING ~ file: charm.py ~ line 103 ~ self.database.relations: {self.database.relations}"
        )
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data.get("username"),
            "password": relation_data.get("password"),
            "endpoints": relation_data.get("endpoints"),
        }

    def _run_sql_migration(self) -> bool:
        """Runs database migration.

        Returns True if migration was run successfully, else returns false.
        """
        try:
            process = self._container.exec(
                ["kratos", "migrate", "sql", "-e", "--config", self._config_file_path, "--yes"],
            )
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            return False

        stdout, _ = process.wait_output()
        logger.info(f"Successfully executed automigration: {stdout}")
        return True

    def _on_pebble_ready(self, event) -> None:
        """Event Handler for pebble ready event."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        self.unit.status = MaintenanceStatus("Configuring/deploying resources")

        with open("src/identity.default.schema.json", encoding="utf-8") as schema_file:
            schema = schema_file.read()
            self._container.push(self._identity_schema_file_path, schema, make_dirs=True)
        self._container.push(self._config_file_path, self._config, make_dirs=True)
        self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
        logger.info("Pebble plan updated with new configuration, replanning")
        self._container.replan()

        # in case container was terminated unexpectedly
        if self.database.is_database_created():
            self._container.start(self._container_name)
            self.unit.status = ActiveStatus()
            return

        if self.model.relations["pg-database"]:
            self.unit.status = WaitingStatus("Waiting for database creation")
        else:
            self.unit.status = BlockedStatus("Missing postgres database relation")

    def _on_database_created(self, event) -> None:
        """Event Handler for database created event."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        self.unit.status = MaintenanceStatus(
            "Configuring container and resources for database connection"
        )

        try:
            self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            event.defer()
            self.unit.status = WaitingStatus("Waiting for Kratos service")
            logger.info("Kratos service is absent. Deferring database created event.")
            return

        logger.info("Updating Kratos config and restarting service")
        self._container.push(self._config_file_path, self._config, make_dirs=True)

        if self.unit.is_leader() and not self._run_sql_migration():
            self.unit.status = BlockedStatus("Database migration failed.")
        else:
            self._container.start(self._container_name)
            self.unit.status = ActiveStatus()

    def _on_database_changed(self, event: DatabaseCreatedEvent) -> None:
        """Event Handler for database changed event."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        self.unit.status = MaintenanceStatus("Updating database details")

        try:
            self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            event.defer()
            self.unit.status = WaitingStatus("Waiting for Kratos service")
            logger.info("Kratos service is absent. Deferring database created event.")
            return

        self._container.push(self._config_file_path, self._config, make_dirs=True)
        self._container.restart(self._container_name)
        self.unit.status = ActiveStatus()


if __name__ == "__main__":
    main(KratosCharm)
