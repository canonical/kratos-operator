#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Kratos."""

import logging
from functools import cached_property
from os.path import join
from pathlib import Path

from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.hydra.v0.hydra_endpoints import (
    HydraEndpointsRelationDataMissingError,
    HydraEndpointsRequirer,
)
from charms.kratos_external_idp_integrator.v0.kratos_external_provider import (
    ClientConfigChangedEvent,
    ExternalIdpRequirer,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import ExecError, Layer

logger = logging.getLogger(__name__)
KRATOS_ADMIN_PORT = 4434
KRATOS_PUBLIC_PORT = 4433
PEER_RELATION_NAME = "kratos-peers"
PEER_KEY_DB_MIGRATE_VERSION = "db_migrate_version"
DB_MIGRATE_VERSION = "0.11.1"


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = "kratos"
        self._container = self.unit.get_container(self._container_name)
        self._config_dir_path = Path("/etc/config")
        self._config_file_path = self._config_dir_path / "kratos.yaml"
        self._identity_schema_file_path = self._config_dir_path / "identity.default.schema.json"
        self._mappers_dir_path = self._config_dir_path / "claim_mappers"
        self._mappers_local_dir_path = Path("claim_mappers")
        self._db_name = f"{self.model.name}_{self.app.name}"
        self._db_relation_name = "pg-database"
        self._hydra_relation_name = "endpoint-info"

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
            relation_name=self._db_relation_name,
            database_name=self._db_name,
            extra_user_roles="SUPERUSER",
        )

        self.external_provider = ExternalIdpRequirer(self, relation_name="kratos-external-idp")

        self.hydra_endpoints = HydraEndpointsRequirer(
            self, relation_name=self._hydra_relation_name
        )

        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.on[self._hydra_relation_name].relation_changed, self._on_config_changed
        )
        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)
        self.framework.observe(self.admin_ingress.on.ready, self._on_admin_ingress_ready)
        self.framework.observe(self.admin_ingress.on.revoked, self._on_ingress_revoked)
        self.framework.observe(self.public_ingress.on.ready, self._on_public_ingress_ready)
        self.framework.observe(self.public_ingress.on.revoked, self._on_ingress_revoked)
        self.framework.observe(
            self.external_provider.on.client_config_changed, self._on_client_config_changed
        )

    @property
    def _kratos_service_params(self):
        ret = ["--config", str(self._config_file_path)]
        if self.config["dev"]:
            logger.warn("Running Kratos in dev mode, don't do this in production")
            ret.append("--dev")

        return " ".join(ret)

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
                    "command": "kratos serve all " + self._kratos_service_params,
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
    def _domain_url(self):
        return self.config["external_url"] or self.public_ingress.url

    @cached_property
    def _get_available_mappers(self):
        return [
            schema_file.name[: -len("_schema.jsonnet")]
            for schema_file in self._mappers_local_dir_path.iterdir()
        ]

    def _render_conf_file(self) -> None:
        """Render the Kratos configuration file."""
        # Open the template kratos.conf file.
        with open("templates/kratos.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            mappers_path=str(self._mappers_dir_path),
            identity_schema_file_path=self._identity_schema_file_path,
            default_browser_return_url=self.config.get("login_ui_url"),
            public_base_url=self._domain_url,
            login_ui_url=join(self.config.get("login_ui_url"), "login"),
            error_ui_url=join(self.config.get("login_ui_url"), "error"),
            oidc_providers=self.external_provider.get_providers(),
            available_mappers=self._get_available_mappers,
            registration_ui_url=join(self.config.get("login_ui_url"), "registration"),
            db_info=self._get_database_relation_info(),
            oauth2_provider_url=self._get_hydra_endpoint_info(),
            smtp_connection_uri=self.config.get("smtp_connection_uri"),
        )
        return rendered

    def _push_schemas(self):
        for schema_file in self._mappers_local_dir_path.iterdir():
            with open(Path(schema_file)) as f:
                schema = f.read()
            self._container.push(Path(self._config_dir_path, schema_file), schema, make_dirs=True)

    def _get_hydra_endpoint_info(self) -> str:
        # Assign a default value as config file won't accept an empty string
        oauth2_provider_url = "http://127.0.0.1:4445/"
        if self.model.relations[self._hydra_relation_name]:
            try:
                hydra_endpoints = self.hydra_endpoints.get_relation_data()
                oauth2_provider_url = hydra_endpoints["admin_endpoint"]
            except HydraEndpointsRelationDataMissingError:
                logger.info("No hydra endpoint-info relation found, default value will be used")

        return oauth2_provider_url

    def _get_database_relation_info(self) -> dict:
        """Get database info from relation data bag."""
        relation_id = self.database.relations[0].id
        relation_data = self.database.fetch_relation_data()[relation_id]

        return {
            "username": relation_data.get("username"),
            "password": relation_data.get("password"),
            "endpoints": relation_data.get("endpoints"),
            "database_name": self._db_name,
        }

    def _run_sql_migration(self) -> bool:
        """Runs database migration.

        Returns True if migration was run successfully, else returns false.
        """
        try:
            process = self._container.exec(
                [
                    "kratos",
                    "migrate",
                    "sql",
                    "-e",
                    "--config",
                    str(self._config_file_path),
                    "--yes",
                ],
            )
            stdout, _ = process.wait_output()
            logger.info(f"Successfully executed automigration: {stdout}")
        except ExecError as err:
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr}")
            self.unit.status = BlockedStatus("Database migration job failed")
            return False

        return True

    def _update_config_restart_service(self, event) -> None:
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

        if self.database.is_resource_created():
            self._container.push(self._config_file_path, self._render_conf_file(), make_dirs=True)
            self._container.restart(self._container_name)
            self.unit.status = ActiveStatus()
            return

        if self.model.relations[self._db_relation_name]:
            self.unit.status = WaitingStatus("Waiting for database creation")
        else:
            self.unit.status = BlockedStatus("Missing postgres database relation")

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
        self._push_schemas()

        self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
        logger.info("Pebble plan updated with new configuration, replanning")
        self._container.replan()

        # in case container was terminated unexpectedly
        peer_relation = self.model.relations[PEER_RELATION_NAME]
        if (
            peer_relation
            and peer_relation[0].data[self.app].get(PEER_KEY_DB_MIGRATE_VERSION)
            == DB_MIGRATE_VERSION
        ):
            self._container.push(self._config_file_path, self._render_conf_file(), make_dirs=True)
            self._container.start(self._container_name)
            self.unit.status = ActiveStatus()
            return

        if self.model.relations[self._db_relation_name]:
            self.unit.status = WaitingStatus("Waiting for database creation")
        else:
            self.unit.status = BlockedStatus("Missing postgres database relation")

    def _on_config_changed(self, event) -> None:
        """Event Handler for config changed event."""
        self._update_config_restart_service(event)

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
        self._container.push(self._config_file_path, self._render_conf_file(), make_dirs=True)

        peer_relation = self.model.relations[PEER_RELATION_NAME]
        if not peer_relation:
            event.defer()
            self.unit.status = WaitingStatus("Waiting for peer relation.")
            return

        if self.unit.is_leader():
            if not self._run_sql_migration():
                self.unit.status = BlockedStatus("Database migration failed.")
            else:
                peer_relation[0].data[self.app].update(
                    {
                        PEER_KEY_DB_MIGRATE_VERSION: DB_MIGRATE_VERSION,
                    }
                )
                self._container.start(self._container_name)
                self.unit.status = ActiveStatus()
        else:
            if (
                peer_relation[0].data[self.app].get(PEER_KEY_DB_MIGRATE_VERSION)
                == DB_MIGRATE_VERSION
            ):
                self._container.start(self._container_name)
                self.unit.status = ActiveStatus()
            else:
                event.defer()
                self.unit.status = WaitingStatus("Waiting for database migration to complete.")

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Event Handler for database changed event."""
        self._update_config_restart_service(event)

    def _on_admin_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's admin ingress URL: %s", event.url)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

    def _on_client_config_changed(self, event: ClientConfigChangedEvent) -> None:
        domain_url = self._domain_url
        if domain_url is None:
            self.unit.status = BlockedStatus(
                "Cannot add external provider without an external hostname. Please "
                "provide an ingress relation or an external_url config."
            )
            event.defer()
            return

        self.unit.status = MaintenanceStatus(f"Adding external provider: {event.provider}")

        if self.database.is_resource_created():
            self._container.push(self._config_file_path, self._render_conf_file(), make_dirs=True)
            self._container.restart(self._container_name)
            self.unit.status = ActiveStatus()

            self.external_provider.set_relation_registered_provider(
                join(domain_url, f"self-service/methods/oidc/callback/{event.provider_id}"),
                event.provider_id,
                event.relation_id,
            )
        else:
            event.defer()
            logger.info("Database is not created. Deferring event.")


if __name__ == "__main__":
    main(KratosCharm)
