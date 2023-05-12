#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Kratos."""

import base64
import json
import logging
from functools import cached_property
from os.path import join
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import requests
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.hydra.v0.hydra_endpoints import (
    HydraEndpointsRelationDataMissingError,
    HydraEndpointsRequirer,
)
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRelationDataMissingError,
    LoginUIEndpointsRelationMissingError,
    LoginUIEndpointsRequirer,
    LoginUITooManyRelatedAppsError,
)
from charms.kratos.v0.kratos_endpoints import KratosEndpointsProvider
from charms.kratos_external_idp_integrator.v0.kratos_external_provider import (
    ClientConfigChangedEvent,
    ExternalIdpRequirer,
)
from charms.loki_k8s.v0.loki_push_api import (
    LogProxyConsumer,
    LogProxyEndpointDeparted,
    LogProxyEndpointJoined,
    PromtailDigestError,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.traefik_k8s.v1.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from ops.charm import (
    ActionEvent,
    CharmBase,
    ConfigChangedEvent,
    HookEvent,
    InstallEvent,
    PebbleReadyEvent,
    RelationEvent,
)
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, ModelError, WaitingStatus
from ops.pebble import ChangeError, Error, ExecError, Layer

from kratos import KratosAPI
from utils import dict_to_action_output, normalise_url

if TYPE_CHECKING:
    from ops.pebble import LayerDict


logger = logging.getLogger(__name__)
KRATOS_ADMIN_PORT = 4434
KRATOS_PUBLIC_PORT = 4433
PEER_RELATION_NAME = "kratos-peers"
PEER_KEY_DB_MIGRATE_VERSION = "db_migrate_version"
DB_MIGRATE_VERSION = "0.11.1"
DEFAULT_SCHEMA_ID_FILE_NAME = "default.schema"


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._container_name = "kratos"
        self._container = self.unit.get_container(self._container_name)
        self._config_dir_path = Path("/etc/config")
        self._config_file_path = self._config_dir_path / "kratos.yaml"
        self._identity_schemas_default_dir_path = self._config_dir_path / "schemas" / "default"
        self._identity_schemas_config_dir_path = self._config_dir_path / "schemas" / "juju"
        self._identity_schemas_local_dir_path = Path("identity_schemas")
        self._mappers_dir_path = self._config_dir_path / "claim_mappers"
        self._mappers_local_dir_path = Path("claim_mappers")
        self._db_name = f"{self.model.name}_{self.app.name}"
        self._db_relation_name = "pg-database"
        self._hydra_relation_name = "endpoint-info"
        self._login_ui_relation_name = "ui-endpoint-info"
        self._prometheus_scrape_relation_name = "metrics-endpoint"
        self._loki_push_api_relation_name = "logging"
        self._kratos_service_command = "kratos serve all"
        self._log_path = "/var/log/kratos.log"

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

        self.login_ui_endpoints = LoginUIEndpointsRequirer(
            self, relation_name=self._login_ui_relation_name
        )

        self.endpoints_provider = KratosEndpointsProvider(self)

        self.framework.observe(self.on.install, self._on_install)

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=self._prometheus_scrape_relation_name,
            jobs=[
                {
                    "metrics_path": "/metrics/prometheus",
                    "static_configs": [
                        {
                            "targets": ["*:4434"],
                        }
                    ],
                }
            ],
        )

        self.loki_consumer = LogProxyConsumer(
            self,
            log_files=[self._log_path],
            relation_name=self._loki_push_api_relation_name,
            container_name=self._container_name,
        )

        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(
            self.endpoints_provider.on.ready, self._update_kratos_endpoints_relation_data
        )
        self.framework.observe(
            self.on[self._hydra_relation_name].relation_changed, self._on_config_changed
        )
        self.framework.observe(
            self.on[self._login_ui_relation_name].relation_changed, self._on_config_changed
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

        self.framework.observe(
            self.loki_consumer.on.promtail_digest_error,
            self._promtail_error,
        )

        self.framework.observe(
            self.loki_consumer.on.log_proxy_endpoint_joined,
            self._on_loki_consumer_endpoint_joined,
        )

        self.framework.observe(
            self.loki_consumer.on.log_proxy_endpoint_departed,
            self._on_loki_consumer_endpoint_departed,
        )

    @property
    def _kratos_service_params(self) -> str:
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
        pebble_layer: LayerDict = {
            "summary": "kratos layer",
            "description": "pebble config layer for kratos",
            "services": {
                self._container_name: {
                    "override": "replace",
                    "summary": "Kratos Operator layer",
                    "startup": "disabled",
                    "command": '/bin/sh -c "{} {} 2>&1 | tee -a {}"'.format(
                        self._kratos_service_command, self._kratos_service_params, self._log_path
                    ),
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
    def _domain_url(self) -> Optional[str]:
        return normalise_url(self.public_ingress.url) if self.public_ingress.is_ready() else None

    @cached_property
    def _get_available_mappers(self) -> List[str]:
        return [
            schema_file.name[: -len("_schema.jsonnet")]
            for schema_file in self._mappers_local_dir_path.iterdir()
        ]

    def _render_conf_file(self) -> str:
        """Render the Kratos configuration file."""
        # Open the template kratos.conf file.
        with open("templates/kratos.yaml.j2", "r") as file:
            template = Template(file.read())

        default_schema_id, schemas = self._get_identity_schema_config()
        rendered = template.render(
            mappers_path=str(self._mappers_dir_path),
            default_browser_return_url=self._get_login_ui_endpoint_info("default_url"),
            identity_schemas=schemas,
            default_identity_schema_id=default_schema_id,
            public_base_url=self._domain_url,
            login_ui_url=self._get_login_ui_endpoint_info("login_url"),
            error_ui_url=self._get_login_ui_endpoint_info("error_url"),
            oidc_providers=self.external_provider.get_providers(),
            available_mappers=self._get_available_mappers,
            registration_ui_url=self._get_login_ui_endpoint_info("registration_url"),
            db_info=self._get_database_relation_info(),
            oauth2_provider_url=self._get_hydra_endpoint_info(),
            smtp_connection_uri=self.config.get("smtp_connection_uri"),
        )
        return rendered

    def _push_file(self, dst: Path, src: Path = None, content: str = None) -> None:
        if not content:
            if not src:
                raise ValueError("`src` or `content` must be provided.")
            with open(src) as f:
                content = f.read()
        self._container.push(dst, content, make_dirs=True)

    def _push_default_files(self) -> None:
        for schema_file in self._mappers_local_dir_path.iterdir():
            self._push_file(self._mappers_dir_path / schema_file.name, src=schema_file)

        for schema_file in self._identity_schemas_local_dir_path.iterdir():
            self._push_file(
                self._identity_schemas_default_dir_path / schema_file.name, src=schema_file
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

    def _get_login_ui_endpoint_info(self, key: str) -> Optional[str]:
        try:
            login_ui_endpoints = self.login_ui_endpoints.get_login_ui_endpoints()
            return login_ui_endpoints[key]
        except LoginUIEndpointsRelationDataMissingError:
            logger.info("No login ui endpoint-info relation data found")
        except LoginUIEndpointsRelationMissingError:
            logger.info("No login ui-endpoint-info relation found")
        except LoginUITooManyRelatedAppsError:
            logger.info("Too many ui-endpoint-info relation found")
        return None

    def _get_juju_config_identity_schema_config(self) -> Optional[Tuple[str, Dict]]:
        if identity_schemas := self.config.get("identity_schemas"):
            default_schema_id = self.config.get("default_identity_schema_id")
            if not default_schema_id:
                logger.error(
                    "`identity_schemas` configuration was set, but no `default_identity_schema_id` was found"
                )
                logger.warning("Ignoring `identity_schemas` configuration")
                return None

            try:
                schemas = json.loads(identity_schemas)
            except json.JSONDecodeError as e:
                logger.error(f"identity_schemas is not a valid json: {e}")
                logger.warning("Ignoring `identity_schemas` configuration")
                return None

            schemas = {
                schema_id: f"base64://{base64.b64encode(json.dumps(schema).encode()).decode()}"
                for schema_id, schema in schemas.items()
            }
            return default_schema_id, schemas
        return None

    def _get_default_identity_schema_config(self) -> Tuple[Optional[str], Optional[Dict]]:
        schemas = {
            schema_file.stem: f"file://{self._identity_schemas_default_dir_path / schema_file.name}"
            for schema_file in self._identity_schemas_local_dir_path.glob("*.json")
        }
        default_schema_id_file = (
            self._identity_schemas_local_dir_path / DEFAULT_SCHEMA_ID_FILE_NAME
        )
        with open(default_schema_id_file) as f:
            default_schema_id = f.read()
        if default_schema_id not in schemas:
            raise RuntimeError(f"Default schema `{default_schema_id}` can't be found")
        return default_schema_id, schemas

    def _get_identity_schema_config(self) -> Optional[Tuple[str, Dict]]:
        """Get the the default schema id and the identity schemas.

        The identity schemas can come from 2 different sources. We chose them in this order:
        1) If the user has defined some schemas in the juju config, return those
        2) Else return the default identity schemas that come with this operator
        """
        if config_schemas := self._get_juju_config_identity_schema_config():
            default_schema_id, schemas = config_schemas
        else:
            default_schema_id, schemas = self._get_default_identity_schema_config()
        return default_schema_id, schemas

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
            logger.error(f"Exited with code {err.exit_code}. Stderr: {err.stderr!r}")
            self.unit.status = BlockedStatus("Database migration job failed")
            return False

        return True

    def _handle_status_update_config(self, event: HookEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        self.unit.status = MaintenanceStatus("Configuring resources")
        self._container.add_layer(self._container_name, self._pebble_layer, combine=True)

        if not self.model.relations[self._db_relation_name]:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")
            event.defer()
            return

        if not self.database.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            event.defer()
            return

        self._container.push(self._config_file_path, self._render_conf_file(), make_dirs=True)
        # We need to push the layer because this may run before _on_pebble_ready
        try:
            self._container.restart(self._container_name)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus("Failed to restart, please consult the logs")
            return

        self.unit.status = ActiveStatus()

    def _on_install(self, event: InstallEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        self._push_default_files()

    def _on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Event Handler for pebble ready event."""
        self._handle_status_update_config(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Event Handler for config changed event."""
        self._handle_status_update_config(event)

    def _update_kratos_endpoints_relation_data(self, event: RelationEvent) -> None:
        logger.info("Sending endpoints info")

        admin_endpoint = (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_ADMIN_PORT}"
        )
        public_endpoint = (
            f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_PUBLIC_PORT}"
        )
        self.endpoints_provider.send_endpoint_relation_data(admin_endpoint, public_endpoint)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event Handler for database created event."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        self.unit.status = MaintenanceStatus(
            "Configuring container and resources for database connection"
        )

        logger.info("Updating Kratos config and restarting service")
        self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
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

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

        self._handle_status_update_config(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

        self._handle_status_update_config(event)

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

        identity_id = event.params.get("identity-id")
        email = event.params.get("email")
        if identity_id and email:
            event.fail("Only one of identity-id and email can be provided.")
            return
        elif not identity_id and not email:
            event.fail("One of identity-id and email must be provided.")
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
        elif not identity_id and not email:
            event.fail("One of identity-id and email must be provided.")
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
        elif not identity_id and not email:
            event.fail("One of identity-id and email must be provided.")
            return

        if email:
            identity = self.kratos.get_identity_from_email(email)
            if not identity:
                event.fail("Couldn't retrieve identity_id from email.")
                return
            identity_id = identity["id"]

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
            identity = self.kratos.create_identity(traits, "admin_v0", password=password)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        identity_id = identity["id"]
        res = {"identity-id": identity_id}
        event.log(f"Successfully created admin account: {identity_id}.")
        if not password:
            event.log("Creating magic link for resetting admin password.")
            try:
                link = self.kratos.recover_password_with_link(identity_id)
            except requests.exceptions.RequestException as e:
                event.fail(f"Failed to request Kratos API: {e}")
                return
            res["password-reset-link"] = link["recovery_link"]
            res["expires-at"] = link["expires_at"]

        event.set_results(res)

    def _on_run_migration_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        timeout = float(event.params.get("timeout", 120))
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

    def _on_loki_consumer_endpoint_joined(self, event: LogProxyEndpointJoined) -> None:
        logger.info("Loki Push API endpoint joined")

    def _on_loki_consumer_endpoint_departed(self, event: LogProxyEndpointDeparted) -> None:
        logger.info("Loki Push API endpoint departed")

    def _promtail_error(self, event: PromtailDigestError):
        logger.error(event.message)
        self.unit.status = BlockedStatus(event.message)


if __name__ == "__main__":
    main(KratosCharm)
