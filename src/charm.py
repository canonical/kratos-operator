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
from secrets import token_hex
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

import requests
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
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
from charms.loki_k8s.v0.loki_push_api import LogProxyConsumer, PromtailDigestError
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.tempo_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from lightkube import Client
from lightkube.resources.apps_v1 import StatefulSet
from ops.charm import (
    ActionEvent,
    CharmBase,
    ConfigChangedEvent,
    HookEvent,
    InstallEvent,
    LeaderElectedEvent,
    PebbleReadyEvent,
    RelationDepartedEvent,
    RelationEvent,
    RemoveEvent,
    UpgradeCharmEvent,
)
from ops.main import main
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    Relation,
    Secret,
    SecretNotFoundError,
    WaitingStatus,
)
from ops.pebble import ChangeError, Error, ExecError, Layer
from tenacity import before_log, retry, stop_after_attempt, wait_exponential

import config_map
from config_map import IdentitySchemaConfigMap, KratosConfigMap, ProvidersConfigMap
from kratos import KratosAPI
from utils import dict_to_action_output, normalise_url

if TYPE_CHECKING:
    from ops.pebble import LayerDict


logger = logging.getLogger(__name__)
KRATOS_ADMIN_PORT = 4434
KRATOS_PUBLIC_PORT = 4433
PEER_RELATION_NAME = "kratos-peers"
SECRET_LABEL = "cookie_secret"
COOKIE_SECRET_KEY = "cookiesecret"
PEER_KEY_DB_MIGRATE_VERSION = "db_migrate_version"
DEFAULT_SCHEMA_ID_FILE_NAME = "default.schema"
LOG_LEVELS = ["panic", "fatal", "error", "warn", "info", "debug", "trace"]


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._container_name = "kratos"
        self._container = self.unit.get_container(self._container_name)
        self._config_dir_path = Path("/etc/config/kratos")
        self._config_file_path = self._config_dir_path / "kratos.yaml"
        self._identity_schemas_default_dir_path = self._config_dir_path
        self._identity_schemas_config_dir_path = self._config_dir_path / "schemas" / "juju"
        self._identity_schemas_local_dir_path = Path("identity_schemas")
        self._mappers_dir_path = self._config_dir_path
        self._mappers_local_dir_path = Path("claim_mappers")
        self._db_name = f"{self.model.name}_{self.app.name}"
        self._db_relation_name = "pg-database"
        self._hydra_relation_name = "hydra-endpoint-info"
        self._login_ui_relation_name = "ui-endpoint-info"
        self._prometheus_scrape_relation_name = "metrics-endpoint"
        self._loki_push_api_relation_name = "logging"
        self._grafana_dashboard_relation_name = "grafana-dashboard"
        self._tracing_relation_name = "tracing"
        self._kratos_service_command = "kratos serve all"
        self._log_dir = Path("/var/log")
        self._log_path = self._log_dir / "kratos.log"
        self._kratos_config_map_name = "kratos-config"

        self.client = Client(field_manager=self.app.name, namespace=self.model.name)
        self.kratos = KratosAPI(
            f"http://127.0.0.1:{KRATOS_ADMIN_PORT}", self._container, str(self._config_file_path)
        )
        self.kratos_configmap = KratosConfigMap(self.client, self)
        self.schemas_configmap = IdentitySchemaConfigMap(self.client, self)
        self.providers_configmap = ProvidersConfigMap(self.client, self)
        self.service_patcher = KubernetesServicePatch(
            self, [("admin", KRATOS_ADMIN_PORT), ("public", KRATOS_PUBLIC_PORT)]
        )
        self.admin_ingress = IngressPerAppRequirer(
            self,
            relation_name="admin-ingress",
            port=KRATOS_ADMIN_PORT,
            strip_prefix=True,
            redirect_https=False,
        )
        self.public_ingress = IngressPerAppRequirer(
            self,
            relation_name="public-ingress",
            port=KRATOS_PUBLIC_PORT,
            strip_prefix=True,
            redirect_https=False,
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

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=self._prometheus_scrape_relation_name,
            jobs=[
                {
                    "metrics_path": "/metrics/prometheus",
                    "static_configs": [
                        {
                            "targets": [f"*:{KRATOS_ADMIN_PORT}"],
                        }
                    ],
                }
            ],
        )

        self.loki_consumer = LogProxyConsumer(
            self,
            log_files=[str(self._log_path)],
            relation_name=self._loki_push_api_relation_name,
            container_name=self._container_name,
        )
        self.tracing = TracingEndpointRequirer(
            self,
            relation_name=self._tracing_relation_name,
        )

        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name=self._grafana_dashboard_relation_name
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade)
        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.remove, self._on_remove)
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
        self.framework.observe(
            self.on[self._db_relation_name].relation_departed, self._on_database_relation_departed
        )
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

        self.framework.observe(self.tracing.on.endpoint_changed, self._on_config_changed)
        self.framework.observe(self.tracing.on.endpoint_removed, self._on_config_changed)

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
    def _tracing_ready(self) -> bool:
        return self.tracing.is_ready()

    @property
    def _pebble_layer(self) -> Layer:
        container = {
            "override": "replace",
            "summary": "Kratos Operator layer",
            "startup": "disabled",
            "command": '/bin/sh -c "{} {} 2>&1 | tee -a {}"'.format(
                self._kratos_service_command,
                self._kratos_service_params,
                str(self._log_path),
            ),
            "environment": {
                "DSN": self._dsn,
                "SERVE_PUBLIC_BASE_URL": self._public_url,
            },
        }

        if self._tracing_ready:
            container["environment"]["TRACING_PROVIDER"] = "otel"
            container["environment"][
                "TRACING_PROVIDERS_OTLP_SERVER_URL"
            ] = self._get_tracing_endpoint_info()
            container["environment"]["TRACING_PROVIDERS_OTLP_INSECURE"] = True
            container["environment"]["TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO"] = 1

        pebble_layer: LayerDict = {
            "summary": "kratos layer",
            "description": "pebble config layer for kratos",
            "services": {self._container_name: container},
            "checks": {
                "kratos-ready": {
                    "override": "replace",
                    "http": {"url": f"http://localhost:{KRATOS_ADMIN_PORT}/admin/health/ready"},
                },
                "kratos-alive": {
                    "override": "replace",
                    "http": {"url": f"http://localhost:{KRATOS_ADMIN_PORT}/admin/health/alive"},
                },
            },
        }

        return Layer(pebble_layer)

    @property
    def _public_url(self) -> Optional[str]:
        url = self.public_ingress.url
        return normalise_url(url) if url else None

    @property
    def _admin_url(self) -> Optional[str]:
        url = self.admin_ingress.url
        return normalise_url(url) if url else None

    @property
    def _dsn(self) -> Optional[str]:
        db_info = self._get_database_relation_info()
        if not db_info:
            return None

        return "postgres://{username}:{password}@{endpoints}/{database_name}".format(
            username=db_info.get("username"),
            password=db_info.get("password"),
            endpoints=db_info.get("endpoints"),
            database_name=db_info.get("database_name"),
        )

    @property
    def _log_level(self) -> str:
        return self.config["log_level"]

    @cached_property
    def _get_available_mappers(self) -> List[str]:
        return [
            schema_file.name[: -len("_schema.jsonnet")]
            for schema_file in self._mappers_local_dir_path.iterdir()
        ]

    def _validate_config_log_level(self) -> bool:
        is_valid = self._log_level in LOG_LEVELS
        if not is_valid:
            logger.info(f"Invalid configuration value for log_level: {self._log_level}")
            self.unit.status = BlockedStatus("Invalid configuration value for log_level")
        return is_valid

    def _render_conf_file(self) -> str:
        """Render the Kratos configuration file."""
        # Open the template kratos.conf file.
        with open("templates/kratos.yaml.j2", "r") as file:
            template = Template(file.read())

        default_schema_id, schemas = self._get_identity_schema_config()
        oidc_providers = self._get_oidc_providers()
        login_ui_url = self._get_login_ui_endpoint_info("login_url")
        mappers = self._get_claims_mappers()
        rendered = template.render(
            cookie_secrets=[self._get_secret()],
            log_level=self._log_level,
            mappers=mappers,
            default_browser_return_url=self._get_login_ui_endpoint_info("login_url"),
            allowed_return_urls=[login_ui_url] if login_ui_url else [],
            identity_schemas=schemas,
            default_identity_schema_id=default_schema_id,
            login_ui_url=login_ui_url,
            error_ui_url=self._get_login_ui_endpoint_info("error_url"),
            oidc_providers=oidc_providers,
            available_mappers=self._get_available_mappers,
            oauth2_provider_url=self._get_hydra_endpoint_info(),
            smtp_connection_uri=self.config.get("smtp_connection_uri"),
        )
        return rendered

    @retry(
        wait=wait_exponential(multiplier=3, min=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
        before=before_log(logger, logging.DEBUG),
    )
    def _update_config(self) -> None:
        conf = self._render_conf_file()
        self.kratos_configmap.update({"kratos.yaml": conf})

    def _get_hydra_endpoint_info(self) -> Optional[str]:
        oauth2_provider_url = None
        if self.model.relations[self._hydra_relation_name]:
            try:
                hydra_endpoints = self.hydra_endpoints.get_hydra_endpoints()
                oauth2_provider_url = hydra_endpoints["admin_endpoint"]
            except HydraEndpointsRelationDataMissingError:
                logger.info("No hydra-endpoint-info relation data found")
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

    def _get_juju_config_identity_schemas(self) -> Optional[Dict]:
        identity_schemas = self.config.get("identity_schemas")
        if not identity_schemas:
            return None
        try:
            schemas = json.loads(identity_schemas)
        except json.JSONDecodeError as e:
            logger.error(f"identity_schemas is not a valid json: {e}")
            logger.warning("Ignoring `identity_schemas` configuration")
            return None
        return {name: json.dumps(s) for name, s in schemas.items()}

    def _get_juju_config_identity_schema_config(self) -> Optional[Tuple[str, Dict]]:
        if identity_schemas := self._get_juju_config_identity_schemas():
            default_schema_id = self.config.get("default_identity_schema_id")
            if not default_schema_id:
                logger.error(
                    "`identity_schemas` configuration was set, but no `default_identity_schema_id` was found"
                )
                logger.warning("Ignoring `identity_schemas` configuration")
                return None

            schemas = {
                schema_id: f"base64://{base64.b64encode(schema.encode()).decode()}"
                for schema_id, schema in identity_schemas.items()
            }
            return default_schema_id, schemas
        return None

    def _get_configmap_identity_schema_config(self) -> Optional[Tuple[str, Dict]]:
        identity_schemas = self.schemas_configmap.get()
        if not identity_schemas:
            return None

        default_schema_id = identity_schemas.pop("default.schema")
        if not default_schema_id:
            logger.error("`configMap with identity schemas contains no `default.schema`")
            return None

        schemas = {
            schema_id: f"base64://{base64.b64encode(schema.encode()).decode()}"
            for schema_id, schema in identity_schemas.items()
        }
        return default_schema_id, schemas

    def _get_default_identity_schemas(self) -> Dict:
        schemas = {}
        for schema_file in self._identity_schemas_local_dir_path.glob("*.json"):
            with open(schema_file) as f:
                schema = f.read()
            schemas[schema_file.stem] = schema
        return schemas

    def _get_default_identity_schema_config(self) -> Tuple[str, Dict]:
        schemas = self._get_default_identity_schemas()
        default_schema_id_file = (
            self._identity_schemas_local_dir_path / DEFAULT_SCHEMA_ID_FILE_NAME
        )
        with open(default_schema_id_file) as f:
            default_schema_id = f.read()
        if default_schema_id not in schemas:
            raise RuntimeError(f"Default schema `{default_schema_id}` can't be found")
        schemas = {
            schema_id: f"base64://{base64.b64encode(schema.encode()).decode()}"
            for schema_id, schema in schemas.items()
        }
        return default_schema_id, schemas

    def _get_identity_schema_config(self) -> Tuple[str, Dict]:
        """Get the the default schema id and the identity schemas.

        The identity schemas can come from 2 different sources. We chose them in this order:
        1) If the user has defined some schemas in the juju config, return those
        2) Else return the default identity schemas that come with this operator
        """
        if config_schemas := self._get_juju_config_identity_schema_config():
            default_schema_id, schemas = config_schemas
        elif config_schemas := self._get_configmap_identity_schema_config():
            default_schema_id, schemas = config_schemas
        else:
            default_schema_id, schemas = self._get_default_identity_schema_config()
        return default_schema_id, schemas

    def _set_version(self) -> None:
        version = self.kratos.get_version()
        self.unit.set_workload_version(version)

    def _get_claims_mappers(self) -> str:
        mappers = {}
        for file in self._mappers_local_dir_path.glob("*.jsonnet"):
            with open(file) as f:
                mapper = f.read()
            mappers[file.stem] = mapper
        return {
            provider_id: f"base64://{base64.b64encode(mapper.encode()).decode()}"
            for provider_id, mapper in mappers.items()
        }

    def _get_oidc_providers(self) -> Optional[List]:
        providers = self.external_provider.get_providers()
        if p := self.providers_configmap.get():
            providers.extend(p.values())
        return providers

    def _get_database_relation_info(self) -> Optional[Dict]:
        """Get database info from relation data bag."""
        if not self.database.relations:
            return None

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
            stdout = self.kratos.run_migration(self._dsn)
            logger.info(f"Successfully executed the database migration: {stdout}")
            return True
        except Error as err:
            self.unit.status = BlockedStatus("Database migration job failed")
            err_msg = err.stderr if isinstance(err, ExecError) else err
            logger.error(f"Database migration failed: {err_msg}")

        return False

    @property
    def _migration_peer_data_key(self) -> Optional[str]:
        if not self.database.relations:
            return None
        return f"{PEER_KEY_DB_MIGRATE_VERSION}_{self.database.relations[0].id}"

    @property
    def _peers(self) -> Optional[Relation]:
        """Fetch the peer relation."""
        return self.model.get_relation(PEER_RELATION_NAME)

    def _set_peer_data(self, key: str, data: Union[Dict, str]) -> None:
        """Put information into the peer data bucket."""
        if not (peers := self._peers):
            return
        peers.data[self.app][key] = json.dumps(data)

    def _get_peer_data(self, key: str) -> Union[Dict, str]:
        """Retrieve information from the peer data bucket."""
        if not (peers := self._peers):
            return {}
        data = peers.data[self.app].get(key, "")
        return json.loads(data) if data else {}

    def _pop_peer_data(self, key: str) -> Union[Dict, str]:
        """Retrieve and remove information from the peer data bucket."""
        if not (peers := self._peers):
            return {}
        data = peers.data[self.app].pop(key, "")
        return json.loads(data) if data else {}

    def _get_secret(self) -> Optional[str]:
        try:
            juju_secret = self.model.get_secret(label=SECRET_LABEL)
            return juju_secret.get_content()[COOKIE_SECRET_KEY]
        except SecretNotFoundError:
            return None

    def _create_secret(self) -> Optional[Secret]:
        if not self.unit.is_leader():
            return None

        secret = {COOKIE_SECRET_KEY: token_hex(16)}
        juju_secret = self.model.app.add_secret(secret, label=SECRET_LABEL)
        return juju_secret

    def _migration_is_needed(self) -> Optional[bool]:
        if not self._peers:
            return None

        return self._get_peer_data(self._migration_peer_data_key) != self.kratos.get_version()

    def _handle_status_update_config(self, event: HookEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        if not self._validate_config_log_level():
            return

        self.unit.status = MaintenanceStatus("Configuring resources")

        if not self.model.relations[self._db_relation_name]:
            self.unit.status = BlockedStatus("Missing required relation with postgresql")
            event.defer()
            return

        if not self.database.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            event.defer()
            return

        if not self._peers:
            self.unit.status = WaitingStatus("Waiting for peer relation")
            event.defer()
            return

        if not self._get_secret():
            self.unit.status = WaitingStatus("Waiting for secret creation")
            event.defer()
            return

        if self._migration_is_needed():
            self.unit.status = WaitingStatus("Waiting for database migration")
            event.defer()
            return

        self._cleanup_peer_data()
        self._update_config()
        # We need to push the layer because this may run before _on_pebble_ready
        self._container.add_layer(self._container_name, self._pebble_layer, combine=True)
        try:
            self._container.restart(self._container_name)
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus("Failed to restart, please consult the logs")
            return

        self.unit.status = ActiveStatus()

    def _on_install(self, event: InstallEvent) -> None:
        config_map.create_all()
        # We populate the kratos-config configmap with defaults. This way the service can
        # start without having to wait for the configMap to be updated later on.
        self._update_config()

    def _on_upgrade(self, event: UpgradeCharmEvent) -> None:
        config_map.create_all()
        # We populate the kratos-config configmap with defaults. This way the service can
        # start without having to wait for the configMap to be updated later on.
        self._update_config()

    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        if not self.unit.is_leader():
            return

        if not self._get_secret():
            self._create_secret()

    def _on_pebble_ready(self, event: PebbleReadyEvent) -> None:
        """Event Handler for pebble ready event."""
        self._patch_statefulset()

        # Necessary directory for log forwarding
        if not self._container.can_connect():
            event.defer()
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return
        if not self._container.isdir(str(self._log_dir)):
            self._container.make_dir(path=str(self._log_dir), make_parents=True)
            logger.info(f"Created directory {self._log_dir}")

        self._set_version()
        self._handle_status_update_config(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Event Handler for config changed event."""
        self._handle_status_update_config(event)

    def _on_remove(self, event: RemoveEvent) -> None:
        if not self.unit.is_leader():
            return

        config_map.delete_all()

    def _get_tracing_endpoint_info(self) -> str:
        if not self._tracing_ready:
            return ""

        return self.tracing.otlp_http_endpoint() or ""

    def _update_kratos_endpoints_relation_data(self, event: RelationEvent) -> None:
        logger.info("Sending endpoints info")

        admin_endpoint = (
            self._admin_url
            or f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_ADMIN_PORT}"
        )
        public_endpoint = (
            self._public_url
            or f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_PUBLIC_PORT}"
        )

        admin_endpoint, public_endpoint = (
            admin_endpoint.replace("https", "http"),
            public_endpoint.replace("https", "http"),
        )
        self.endpoints_provider.send_endpoint_relation_data(admin_endpoint, public_endpoint)

    def _patch_statefulset(self) -> None:
        if not self.unit.is_leader():
            return

        pod_spec_patch = {
            "containers": [
                {
                    "name": self._container_name,
                    "volumeMounts": [
                        {
                            "mountPath": str(self._config_dir_path),
                            "name": "config",
                            "readOnly": True,
                        },
                    ],
                },
            ],
            "volumes": [
                {
                    "name": "config",
                    "configMap": {"name": self._kratos_config_map_name},
                },
            ],
        }
        patch = {"spec": {"template": {"spec": pod_spec_patch}}}
        self.client.patch(StatefulSet, name=self.meta.name, namespace=self.model.name, obj=patch)

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        """Event Handler for database created event."""
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring the event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        if not self._peers:
            self.unit.status = WaitingStatus("Waiting for peer relation")
            event.defer()
            return

        if not self._get_secret():
            self.unit.status = WaitingStatus("Waiting for secret creation")
            event.defer()
            return

        if not self._migration_is_needed():
            self._handle_status_update_config(event)
            return

        if not self.unit.is_leader():
            logger.info("Unit does not have leadership")
            self.unit.status = WaitingStatus("Unit waiting for leadership to run the migration")
            event.defer()
            return

        if not self._run_sql_migration():
            self.unit.status = BlockedStatus("Database migration job failed")
            logger.error("Automigration job failed, please use the run-migration action")
            return

        self._set_peer_data(self._migration_peer_data_key, self.kratos.get_version())
        self._handle_status_update_config(event)

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        """Event Handler for database changed event."""
        self._handle_status_update_config(event)

    def _on_database_relation_departed(self, event: RelationDepartedEvent) -> None:
        """Event Handler for database changed event."""
        if event.departing_unit == self.unit:
            return

        self.unit.status = BlockedStatus("Missing required relation with postgresql")
        try:
            self._container.stop(self._container_name)
        except ChangeError as err:
            logger.error(str(err))
            return

    def _cleanup_peer_data(self) -> None:
        if not self._peers:
            return
        # We need to remove the migration key from peer data. We can't do that in relation
        # departed as we can't tell if the event was triggered from a unit dying of the
        # relation being actually departed.
        extra_keys = [
            k
            for k in self._peers.data[self.app].keys()
            if k.startswith(PEER_KEY_DB_MIGRATE_VERSION) and k != self._migration_peer_data_key
        ]
        for k in extra_keys:
            self._pop_peer_data(k)

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
        public_url = self._public_url
        if public_url is None:
            self.unit.status = BlockedStatus(
                "Cannot add external provider without an external hostname. Please "
                "provide an ingress relation or an external_url config."
            )
            event.defer()
            return

        self.unit.status = MaintenanceStatus(f"Adding external provider: {event.provider}")

        if not self._migration_is_needed():
            self._handle_status_update_config(event)

            self.external_provider.set_relation_registered_provider(
                join(public_url, f"self-service/methods/oidc/callback/{event.provider_id}"),
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
        if not self._container.can_connect():
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        timeout = float(event.params.get("timeout", 120))
        event.log("Migrating database.")
        try:
            self.kratos.run_migration(timeout=timeout, dsn=self._dsn)
        except Error as e:
            err_msg = e.stderr if isinstance(e, ExecError) else e
            event.fail(f"Database migration action failed: {err_msg}")
            return
        event.log("Successfully migrated the database.")

        if not self._peers:
            event.fail("Peer relation not ready. Failed to store migration version")
            return
        self._set_peer_data(self._migration_peer_data_key, self.kratos.get_version())
        event.log("Updated migration version in peer data.")

    def _promtail_error(self, event: PromtailDigestError) -> None:
        logger.error(event.message)


if __name__ == "__main__":
    main(KratosCharm)
