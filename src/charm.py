#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Kratos."""

import logging

from charms.data_platform_libs.v0.database_requires import DatabaseCreatedEvent, DatabaseRequires
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus
from ops.pebble import ChangeError, ExecError, Layer

logger = logging.getLogger(__name__)
KRATOS_ADMIN_PORT = 4434
KRATOS_PUBLIC_PORT = 4433


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = "kratos"
        self._container = self.unit.get_container(self._container_name)
        self._config_dir_path = "/etc/config"
        self._config_file_path = f"{self._config_dir_path}/kratos.yaml"
        self._identity_schema_file_path = f"{self._config_dir_path}/identity.default.schema.json"
        self._db_name = f"{self.model.name}_{self.app.name}"

        self.service_patcher = KubernetesServicePatch(
            self, [("admin", KRATOS_ADMIN_PORT), ("public", KRATOS_PUBLIC_PORT)]
        )
        self.admin_ingress = IngressPerAppRequirer(
            self,
            relation_name="admin-ingress",
            port=KRATOS_ADMIN_PORT,
            strip_prefix=True,
        )
        self.public_ingress = IngressPerAppRequirer(
            self,
            relation_name="public-ingress",
            port=KRATOS_PUBLIC_PORT,
            strip_prefix=True,
        )

        self.database = DatabaseRequires(
            self,
            relation_name="pg-database",
            database_name=self._db_name,
            extra_user_roles="SUPERUSER",
        )

        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.database.on.database_created, self._on_database_changed)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)
        self.framework.observe(self.admin_ingress.on.ready, self._on_admin_ingress_ready)
        self.framework.observe(self.admin_ingress.on.revoked, self._on_ingress_revoked)
        self.framework.observe(self.public_ingress.on.ready, self._on_public_ingress_ready)
        self.framework.observe(self.public_ingress.on.revoked, self._on_ingress_revoked)

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

    def _render_conf_file(self) -> None:
        """Render the Kratos configuration file."""
        # Open the template kratos.conf file.
        with open("templates/kratos.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            identity_schema_file_path=self._identity_schema_file_path,
            default_browser_return_url="http://127.0.0.1:9999/",
            login_ui_url="http://localhost:4455/login",
            registration_ui_url="http://127.0.0.1:9999/registration",
            db_info=self._get_database_relation_info(),
            smtp_connection_uri="smtps://test:test@mailslurper:1025/?skip_ssl_verify=true",
        )
        return rendered

    def _update_layer(self) -> None:
        """Updates the Pebble configuration layer and kratos config if changed."""
        config = self._render_conf_file()
        if not self._container.get_plan().to_dict():
            self.unit.status = MaintenanceStatus("Applying new pebble layer")
            self._container.push(self._config_file_path, config, make_dirs=True)
            with open("src/identity.default.schema.json", encoding="utf-8") as schema_file:
                schema = schema_file.read()
                self._container.push(self._identity_schema_file_path, schema, make_dirs=True)
            self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
            logger.info("Pebble plan updated with new configuration, replanning")
            self._container.replan()
        else:
            # Compare changes in kratos config
            current_config = self._container.pull(self._config_file_path).read()
            if current_config != config:
                self.unit.status = MaintenanceStatus("Updating Kratos Config")
                self._container.push(self._config_file_path, config, make_dirs=True)
                logger.info("Updated kratos config")
                self._container.restart(self._container_name)

    def _get_database_relation_info(self) -> dict:
        """Get database info from relation data bag."""
        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data["username"],
            "password": relation_data["password"],
            "endpoints": relation_data["endpoints"],
            "database_name": self._db_name,
        }

    def _update_container(self, event) -> None:
        """Update configs, pebble layer and run database migration."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        if not self.model.relations["pg-database"]:
            logger.error("Missing required relation with postgresql")
            self.model.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self.database.is_database_created():
            event.defer()
            logger.info("Missing database details. Deferring event.")
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        try:
            self._update_layer()
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus("Failed to replan")
            return

        if not self.unit.is_leader():
            return

        self._run_sql_migration()

        self.unit.status = ActiveStatus()

    def _run_sql_migration(self) -> None:
        """Runs database migration."""
        process = self._container.exec(
            ["kratos", "migrate", "sql", "-e", "--config", self._config_file_path, "--yes"],
            timeout=20.0,
        )
        try:
            stdout, _ = process.wait_output()
            logger.info(f"Successfully executed automigration: {stdout}")
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            self.unit.status = BlockedStatus("Database migration job failed")

    def _on_pebble_ready(self, event) -> None:
        """Event Handler for pebble ready event."""
        self.unit.status = MaintenanceStatus("Configuring/deploying resources")
        self._update_container(event)

    def _on_database_changed(self, event: DatabaseCreatedEvent) -> None:
        """Event Handler for database created event."""
        self.unit.status = MaintenanceStatus("Retrieving database details")
        self._update_container(event)

    def _on_admin_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's admin ingress URL: %s", event.url)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")


if __name__ == "__main__":
    main(KratosCharm)
