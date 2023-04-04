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
from typing import Optional

import requests
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.hydra.v0.hydra_endpoints import (
    HydraEndpointsRelationDataMissingError,
    HydraEndpointsRequirer,
)
from charms.kratos.v0.kratos_endpoints import KratosEndpointsProvider
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
from ops.charm import ActionEvent, CharmBase, HookEvent, RelationEvent
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import Error, ExecError, Layer

from kratos import KratosAPI

logger = logging.getLogger(__name__)
KRATOS_ADMIN_PORT = 4434
KRATOS_PUBLIC_PORT = 4433
PEER_RELATION_NAME = "kratos-peers"
PEER_KEY_DB_MIGRATE_VERSION = "db_migrate_version"
DB_MIGRATE_VERSION = "0.11.1"


def dict_to_action_output(d):
    """Convert all keys in a dict to the format of a juju action output."""
    ret = {}
    for k, v in d.items():
        k = k.replace("_", "-")
        if isinstance(v, dict):
            v = dict_to_action_output(v)
        ret[k] = v
    return ret


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args):
        super().__init__(*args)
        self._container_name = "kratos"
        self._container = self.unit.get_container(self._container_name)
        self._config_dir_path = Path("/etc/config")
        self._config_file_path = self._config_dir_path / "kratos.yaml"
        self._identity_schema_file_path = self._config_dir_path / "identity.default.schema.json"
        self._admin_identity_schema_file_path = (
            self._config_dir_path / "identity.admin.schema.json"
        )
        self._mappers_dir_path = self._config_dir_path / "claim_mappers"
        self._mappers_local_dir_path = Path("claim_mappers")
        self._db_name = f"{self.model.name}_{self.app.name}"
        self._db_relation_name = "pg-database"
        self._hydra_relation_name = "endpoint-info"

        self.kratos = KratosAPI(
            f"http://127.0.0.1:{KRATOS_ADMIN_PORT}", self._container, str(self._config_file_path)
        )
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

        self.endpoints_provider = KratosEndpointsProvider(self)

        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.endpoints_provider.on.ready, self._update_kratos_endpoints_relation_data
        )
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

        self.framework.observe(self.on.get_identity_action, self._on_get_identity_action)
        self.framework.observe(self.on.delete_identity_action, self._on_delete_identity_action)
        # TODO: Uncomment this line after we have implemented the recovery endpoint
        # self.framework.observe(self.on.reset_password_action, self._on_reset_password_action)
        self.framework.observe(
            self.on.create_admin_account_action, self._on_create_admin_account_action
        )
        self.framework.observe(self.on.run_migration_action, self._on_run_migration_action)

    @property
    def _kratos_service_params(self):
        ret = ["--config", str(self._config_file_path)]
        if self.config["dev"]:
            logger.warning("Running Kratos in dev mode, don't do this in production")
            ret.append("--dev")

        return " ".join(ret)

    @property
    def _kratos_service_is_running(self) -> bool:
        if not self._container.can_connect():
            return False

        try:
            service = self._container.get_service(self._container_name)
        except (ModelError, RuntimeError):
            return False
        return service.is_running()

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

    def _render_conf_file(self) -> str:
        """Render the Kratos configuration file."""
        # Open the template kratos.conf file.
        with open("templates/kratos.yaml.j2", "r") as file:
            template = Template(file.read())

        rendered = template.render(
            mappers_path=str(self._mappers_dir_path),
            identity_schema_file_path=self._identity_schema_file_path,
            admin_identity_schema_file_path=self._admin_identity_schema_file_path,
            default_browser_return_url=self.config.get("login_ui_url"),
            public_base_url=self._domain_url,
            login_ui_url=join(self.config.get("login_ui_url"), "login"),
            error_ui_url=join(self.config.get("login_ui_url"), "oidc_error"),
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
            self._container.push(
                path=Path(self._config_dir_path, schema_file), source=schema, make_dirs=True
            )

    def _get_hydra_endpoint_info(self) -> Optional[str]:
        oauth2_provider_url = None
        if self.model.relations[self._hydra_relation_name]:
            try:
                hydra_endpoints = self.hydra_endpoints.get_hydra_endpoints()
                oauth2_provider_url = hydra_endpoints["admin_endpoint"]
            except HydraEndpointsRelationDataMissingError:
                logger.info("No hydra endpoint-info relation data found")
                return None

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

    def _handle_status_update_config(self, event: HookEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        self.unit.status = MaintenanceStatus("Configuring/deploying resources")

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

        with open("src/identity.admin.schema.json", encoding="utf-8") as schema_file:
            schema = schema_file.read()
            self._container.push(self._admin_identity_schema_file_path, schema, make_dirs=True)

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
        self._handle_status_update_config(event)

    def _update_kratos_endpoints_relation_data(self, event: RelationEvent) -> None:
        admin_endpoint = (
            self.admin_ingress.url
            if self.admin_ingress.is_ready()
            else f"{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_ADMIN_PORT}",
        )
        public_endpoint = (
            self.public_ingress.url
            if self.public_ingress.is_ready()
            else f"{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_PUBLIC_PORT}",
        )

        logger.info(
            f"Sending endpoints info: public - {public_endpoint[0]}, admin - {admin_endpoint[0]}"
        )

        self.endpoints_provider.send_endpoint_relation_data(admin_endpoint[0], public_endpoint[0])

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
        self._handle_status_update_config(event)

    def _on_admin_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's admin ingress URL: %s", event.url)

        self._handle_status_update_config(event)
        self._update_kratos_endpoints_relation_data(event)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

        self._handle_status_update_config(event)
        self._update_kratos_endpoints_relation_data(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

        self._handle_status_update_config(event)
        self._update_kratos_endpoints_relation_data(event)

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

    def _on_get_identity_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        event.log("Getting the identity.")
        identity_id = event.params.get("identity-id")
        email = event.params.get("email")
        if identity_id and email:
            event.fail("Only one of identity-id and email can be provided.")
            return

        event.log("Fetching the identity.")
        if email:
            try:
                identity = self.kratos.get_identity_from_email(email)
            except Error as e:
                event.fail(f"Something went wrong when trying to run the command: {e}")
                return
            if not identity:
                event.fail("Couldn't retrieve identity_id from email.")
                return
        else:
            try:
                identity = self.kratos.get_identity(identity_id=identity_id)
            except Error as e:
                event.fail(f"Something went wrong when trying to run the command: {e}")
                return

        event.log("Successfully got the identity.")
        event.set_results(dict_to_action_output(identity))

    def _on_delete_identity_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = event.params.get("identity-id")
        email = event.params.get("email")
        if identity_id and email:
            event.fail("Only one of identity-id and email can be provided.")
            return

        if email:
            identity = self.kratos.get_identity_from_email(email)
            if not identity:
                event.fail("Couldn't retrieve identity_id from email.")
                return

        event.log("Deleting the identity.")
        try:
            self.kratos.delete_identity(identity_id=identity_id)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log(f"Successfully deleted the identity: {identity_id}.")
        event.set_results({"idenity-id": identity_id})

    def _on_reset_password_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = event.params.get("identity-id")
        email = event.params.get("email")
        recovery_method = event.params.get("recovery-method")
        if identity_id and email:
            event.fail("Only one of identity-id and email can be provided.")
            return

        if email:
            identity = self.kratos.get_identity_from_email(email)
            if not identity:
                event.fail("Couldn't retrieve identity_id from email.")
                return

        if recovery_method == "code":
            fun = self.kratos.recover_password_with_code
        elif recovery_method == "link":
            fun = self.kratos.recover_password_with_link
        else:
            event.fail(
                f"Unsupported recovery method {recovery_method}, "
                "allowed methods are: `code` and `link`"
            )
            return

        event.log("Resetting password.")
        try:
            ret = fun(identity_id=identity_id)
        except requests.exceptions.RequestException as e:
            event.fail(f"Failed to request Kratos API: {e}")
            return

        event.log("Follow the link to reset the user's password")
        event.set_results(dict_to_action_output(ret))

    def _on_create_admin_account_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        traits = {
            "username": event.params["username"],
            "name": event.params.get("name"),
            "email": event.params.get("email"),
            "phone_number": event.params.get("phone_number"),
        }
        traits = {k: v for k, v in traits.items() if v is not None}
        password = event.params.get("password")

        event.log("Creating admin account.")
        try:
            identity = self.kratos.create_identity(traits, "admin", password=password)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        identity_id = identity["id"]
        res = {"identity-id": identity_id}
        event.log(f"Successfully created admin account: {identity_id}.")
        if not password:
            event.log("Creating magic link for resetting admin password.")
            link = self.kratos.recover_password_with_link(identity_id)
            res["password-reset-link"] = link["recovery_link"]
            res["expires-at"] = link["expires_at"]

        event.set_results(res)

    def _on_run_migration_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        timeout = event.params.get("timeout")
        event.log("Migrating database.")
        try:
            _, err = self.kratos.run_migration(timeout=timeout)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        if err:
            event.fail(f"Something went wrong when running the migration: {err}")
            return
        event.log("Successfully migrated the database.")


if __name__ == "__main__":
    main(KratosCharm)
