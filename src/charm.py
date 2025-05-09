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
from secrets import token_hex
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

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
    LoginUIEndpointsRequirer,
)
from charms.kratos.v0.kratos_info import KratosInfoProvider
from charms.kratos.v0.kratos_registration_webhook import KratosRegistrationWebhookRequirer
from charms.kratos_external_idp_integrator.v0.kratos_external_provider import (
    ClientConfigChangedEvent,
    ClientConfigRemovedEvent,
    ExternalIdpRequirer,
    Provider,
)
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.observability_libs.v0.kubernetes_service_patch import KubernetesServicePatch
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.smtp_integrator.v0.smtp import SmtpDataAvailableEvent, SmtpRequires
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from jinja2 import Template
from lightkube import Client
from lightkube.resources.apps_v1 import StatefulSet
from ops import main
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
    RelationJoinedEvent,
    RemoveEvent,
    UpgradeCharmEvent,
)
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
from certificate_transfer_integration import CertTransfer
from config_map import IdentitySchemaConfigMap, KratosConfigMap, ProvidersConfigMap
from constants import (
    CONFIG_DIR_PATH,
    CONFIG_FILE_PATH,
    COOKIE_SECRET_KEY,
    DB_RELATION_NAME,
    DEFAULT_SCHEMA_ID_FILE_NAME,
    EMAIL_TEMPLATE_FILE_PATH,
    GRAFANA_DASHBOARD_RELATION_NAME,
    HYDRA_RELATION_NAME,
    IDENTITY_SCHEMAS_LOCAL_DIR_PATH,
    INTERNAL_INGRESS_RELATION_NAME,
    KRATOS_ADMIN_PORT,
    KRATOS_CONFIG_MAP_NAME,
    KRATOS_EXTERNAL_IDP_INTEGRATOR_RELATION_NAME,
    KRATOS_INFO_RELATION_NAME,
    KRATOS_PUBLIC_PORT,
    KRATOS_SERVICE_COMMAND,
    LOG_LEVELS,
    LOGIN_UI_RELATION_NAME,
    LOKI_PUSH_API_RELATION_NAME,
    MAPPERS_LOCAL_DIR_PATH,
    PEER_KEY_DB_MIGRATE_VERSION,
    PEER_RELATION_NAME,
    PROMETHEUS_SCRAPE_RELATION_NAME,
    PROVIDERS_CONFIGMAP_FILE_NAME,
    REGISTRATION_WEBHOOK_RELATION_NAME,
    SECRET_LABEL,
    TRACING_RELATION_NAME,
    WORKLOAD_CONTAINER_NAME,
)
from kratos import KratosAPI
from utils import dict_to_action_output, normalise_url, run_after_config_updated

if TYPE_CHECKING:
    from ops.pebble import LayerDict


logger = logging.getLogger(__name__)


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self._container = self.unit.get_container(WORKLOAD_CONTAINER_NAME)

        self.client = Client(field_manager=self.app.name, namespace=self.model.name)
        self.kratos = KratosAPI(f"http://127.0.0.1:{KRATOS_ADMIN_PORT}", self._container)
        self.kratos_configmap = KratosConfigMap(self.client, self)
        self.schemas_configmap = IdentitySchemaConfigMap(self.client, self)
        self.providers_configmap = ProvidersConfigMap(self.client, self)
        self.service_patcher = KubernetesServicePatch(
            self, [("admin", KRATOS_ADMIN_PORT), ("public", KRATOS_PUBLIC_PORT)]
        )
        self.smtp = SmtpRequires(self)
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

        # -- ingress via raw traefik_route
        # TraefikRouteRequirer expects an existing relation to be passed as part of the constructor,
        # so this may be none. Rely on `self.ingress.is_ready` later to check
        self.internal_ingress = TraefikRouteRequirer(
            self,
            self.model.get_relation(INTERNAL_INGRESS_RELATION_NAME),
            INTERNAL_INGRESS_RELATION_NAME,
        )  # type: ignore

        self.database = DatabaseRequires(
            self,
            relation_name=DB_RELATION_NAME,
            database_name=f"{self.model.name}_{self.app.name}",
            extra_user_roles="SUPERUSER",
        )

        self.external_provider = ExternalIdpRequirer(
            self, relation_name=KRATOS_EXTERNAL_IDP_INTEGRATOR_RELATION_NAME
        )

        self.hydra_endpoints = HydraEndpointsRequirer(self, relation_name=HYDRA_RELATION_NAME)

        self.registration_webhook = KratosRegistrationWebhookRequirer(
            self, relation_name=REGISTRATION_WEBHOOK_RELATION_NAME
        )
        self.login_ui_endpoints = LoginUIEndpointsRequirer(
            self, relation_name=LOGIN_UI_RELATION_NAME
        )

        self.info_provider = KratosInfoProvider(self)

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=PROMETHEUS_SCRAPE_RELATION_NAME,
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

        self._log_forwarder = LogForwarder(self, relation_name=LOKI_PUSH_API_RELATION_NAME)
        self.tracing = TracingEndpointRequirer(
            self, relation_name=TRACING_RELATION_NAME, protocols=["otlp_http"]
        )

        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name=GRAFANA_DASHBOARD_RELATION_NAME
        )

        self.cert_transfer = CertTransfer(
            self,
            WORKLOAD_CONTAINER_NAME,
            self._handle_status_update_config,
        )

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER_NAME,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade)
        self.framework.observe(self.on.kratos_pebble_ready, self._on_pebble_ready)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.update_status, self._handle_status_update_config)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(self.info_provider.on.ready, self._update_kratos_info_relation_data)
        self.framework.observe(
            self.registration_webhook.on.ready, self._handle_status_update_config
        )
        self.framework.observe(
            self.registration_webhook.on.unavailable, self._handle_status_update_config
        )
        self.framework.observe(
            self.on[HYDRA_RELATION_NAME].relation_changed, self._on_config_changed
        )
        self.framework.observe(
            self.on[LOGIN_UI_RELATION_NAME].relation_changed, self._on_config_changed
        )
        self.framework.observe(self.database.on.database_created, self._on_database_created)
        self.framework.observe(self.database.on.endpoints_changed, self._on_database_changed)
        self.framework.observe(
            self.on[DB_RELATION_NAME].relation_departed, self._on_database_relation_departed
        )
        self.framework.observe(self.admin_ingress.on.ready, self._on_admin_ingress_ready)
        self.framework.observe(self.admin_ingress.on.revoked, self._on_ingress_revoked)
        self.framework.observe(self.public_ingress.on.ready, self._on_public_ingress_ready)
        self.framework.observe(self.public_ingress.on.revoked, self._on_ingress_revoked)
        self.framework.observe(
            self.external_provider.on.client_config_changed, self._on_client_config_changed
        )
        self.framework.observe(
            self.external_provider.on.client_config_removed, self._on_client_config_removed
        )
        self.framework.observe(self.smtp.on.smtp_data_available, self._on_smtp_data_available)

        self.framework.observe(self.on.get_identity_action, self._on_get_identity_action)
        self.framework.observe(self.on.delete_identity_action, self._on_delete_identity_action)
        self.framework.observe(self.on.reset_password_action, self._on_reset_password_action)
        self.framework.observe(
            self.on.invalidate_identity_sessions_action,
            self._on_invalidate_identity_sessions_action,
        )
        self.framework.observe(
            self.on.reset_identity_mfa_action, self._on_reset_identity_mfa_action
        )
        self.framework.observe(
            self.on.create_admin_account_action, self._on_create_admin_account_action
        )
        self.framework.observe(self.on.run_migration_action, self._on_run_migration_action)

        self.framework.observe(self.tracing.on.endpoint_changed, self._on_config_changed)
        self.framework.observe(self.tracing.on.endpoint_removed, self._on_config_changed)

        self.framework.observe(
            self.on[INTERNAL_INGRESS_RELATION_NAME].relation_joined,
            self._configure_internal_ingress,
        )
        self.framework.observe(
            self.on[INTERNAL_INGRESS_RELATION_NAME].relation_changed,
            self._configure_internal_ingress,
        )
        self.framework.observe(
            self.on[INTERNAL_INGRESS_RELATION_NAME].relation_broken,
            self._configure_internal_ingress,
        )
        self.framework.observe(self.on.leader_elected, self._configure_internal_ingress)
        self.framework.observe(self.on.config_changed, self._configure_internal_ingress)

        # resource patching
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

    @property
    def _http_proxy(self) -> str:
        return self.config["http_proxy"]

    @property
    def _https_proxy(self) -> str:
        return self.config["https_proxy"]

    @property
    def _no_proxy(self) -> str:
        return self.config["no_proxy"]

    @property
    def _kratos_service_params(self) -> str:
        ret = ["--config", str(CONFIG_FILE_PATH)]
        if self.config["dev"]:
            logger.warning("Running Kratos in dev mode, don't do this in production")
            ret.append("--dev")

        return " ".join(ret)

    @property
    def _kratos_service_is_running(self) -> bool:
        if not self._container.can_connect():
            return False

        try:
            service = self._container.get_service(WORKLOAD_CONTAINER_NAME)
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
            "command": f"{KRATOS_SERVICE_COMMAND} {self._kratos_service_params}",
            "environment": {
                "DSN": self._dsn,
                "SERVE_PUBLIC_BASE_URL": self._public_url,
                "HTTP_PROXY": self._http_proxy,
                "HTTPS_PROXY": self._https_proxy,
                "NO_PROXY": self._no_proxy,
            },
        }

        if self._tracing_ready:
            container["environment"]["TRACING_PROVIDER"] = "otel"
            container["environment"]["TRACING_PROVIDERS_OTLP_SERVER_URL"] = (
                self._get_tracing_endpoint_info()
            )
            container["environment"]["TRACING_PROVIDERS_OTLP_INSECURE"] = True
            container["environment"]["TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO"] = 1

        pebble_layer: LayerDict = {
            "summary": "kratos layer",
            "description": "pebble config layer for kratos",
            "services": {WORKLOAD_CONTAINER_NAME: container},
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
    def _internal_url(self) -> Optional[str]:
        host = self.internal_ingress.external_host
        return (
            f"{self.internal_ingress.scheme}://{host}/{self.model.name}-{self.model.app.name}"
            if host
            else None
        )

    @property
    def _internal_ingress_config(self) -> dict:
        """Build a raw ingress configuration for Traefik."""
        # The path prefix is the same as in ingress per app
        external_path = f"{self.model.name}-{self.model.app.name}"

        middlewares = {
            f"juju-sidecar-noprefix-{self.model.name}-{self.model.app.name}": {
                "stripPrefix": {"forceSlash": False, "prefixes": [f"/{external_path}"]},
            },
        }

        routers = {
            f"juju-{self.model.name}-{self.model.app.name}-admin-api-router": {
                "entryPoints": ["web"],
                "rule": f"PathPrefix(`/{external_path}/admin`)",
                "middlewares": list(middlewares.keys()),
                "service": f"juju-{self.model.name}-{self.app.name}-admin-api-service",
            },
            f"juju-{self.model.name}-{self.model.app.name}-admin-api-router-tls": {
                "entryPoints": ["websecure"],
                "rule": f"PathPrefix(`/{external_path}/admin`)",
                "middlewares": list(middlewares.keys()),
                "service": f"juju-{self.model.name}-{self.app.name}-admin-api-service",
                "tls": {
                    "domains": [
                        {
                            "main": self.internal_ingress.external_host,
                            "sans": [f"*.{self.internal_ingress.external_host}"],
                        },
                    ],
                },
            },
            f"juju-{self.model.name}-{self.model.app.name}-public-api-router": {
                "entryPoints": ["web"],
                "rule": f"PathPrefix(`/{external_path}`)",
                "middlewares": list(middlewares.keys()),
                "service": f"juju-{self.model.name}-{self.app.name}-public-api-service",
            },
            f"juju-{self.model.name}-{self.model.app.name}-public-api-router-tls": {
                "entryPoints": ["websecure"],
                "rule": f"PathPrefix(`/{external_path}`)",
                "middlewares": list(middlewares.keys()),
                "service": f"juju-{self.model.name}-{self.app.name}-public-api-service",
                "tls": {
                    "domains": [
                        {
                            "main": self.internal_ingress.external_host,
                            "sans": [f"*.{self.internal_ingress.external_host}"],
                        },
                    ],
                },
            },
        }

        services = {
            f"juju-{self.model.name}-{self.app.name}-admin-api-service": {
                "loadBalancer": {
                    "servers": [
                        {
                            "url": f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_ADMIN_PORT}"
                        }
                    ]
                }
            },
            f"juju-{self.model.name}-{self.app.name}-public-api-service": {
                "loadBalancer": {
                    "servers": [
                        {
                            "url": f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_PUBLIC_PORT}"
                        }
                    ]
                }
            },
        }

        return {"http": {"routers": routers, "services": services, "middlewares": middlewares}}

    @property
    def _kratos_endpoints(self) -> Tuple[str, str]:
        admin_endpoint = (
            self._internal_url
            or f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_ADMIN_PORT}"
        )
        public_endpoint = (
            self._internal_url
            or f"http://{self.app.name}.{self.model.name}.svc.cluster.local:{KRATOS_PUBLIC_PORT}"
        )

        return admin_endpoint, public_endpoint

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
            for schema_file in MAPPERS_LOCAL_DIR_PATH.iterdir()
        ]

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

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
        registration_webhook_config = self._get_registration_webhook_config()
        mappers = self._get_claims_mappers()
        cookie_secrets = self._get_secret()
        parsed_public_url = urlparse(self._public_url)
        ui_endpoint_info = self._get_login_ui_endpoint_info()

        allowed_return_urls = []
        origin = ""
        if self._public_url:
            allowed_return_urls = [
                parsed_public_url._replace(path="", params="", query="", fragment="").geturl()
                + "/"
            ]
            origin = f"{parsed_public_url.scheme}://{parsed_public_url.hostname}"

        rendered = template.render(
            cookie_secrets=[cookie_secrets] if cookie_secrets else None,
            log_level=self._log_level,
            mappers=mappers,
            default_browser_return_url=ui_endpoint_info.get("login_url"),
            allowed_return_urls=allowed_return_urls,
            identity_schemas=schemas,
            default_identity_schema_id=default_schema_id,
            login_ui_url=ui_endpoint_info.get("login_url"),
            error_ui_url=ui_endpoint_info.get("error_url"),
            settings_ui_url=ui_endpoint_info.get("settings_url"),
            recovery_ui_url=ui_endpoint_info.get("recovery_url"),
            webauthn_settings_url=ui_endpoint_info.get("webauthn_settings_url"),
            registration_ui_url=ui_endpoint_info.get("registration_url"),
            oidc_providers=oidc_providers,
            available_mappers=self._get_available_mappers,
            oauth2_provider_url=self._get_hydra_endpoint_info(),
            smtp_connection_uri=self._smtp_connection_uri,
            recovery_email_template=self._recovery_email_template,
            enable_local_idp=self.config.get("enable_local_idp"),
            enforce_mfa=self.config.get("enforce_mfa"),
            enable_passwordless_login_method=self.config.get("enable_passwordless_login_method"),
            enable_oidc_webauthn_sequencing=self.config.get("enable_oidc_webauthn_sequencing"),
            origin=origin,
            domain=parsed_public_url.hostname,
            registration_webhook_config=registration_webhook_config,
        )
        return rendered

    @property
    def _recovery_email_template(self) -> Optional[str]:
        if self.config.get("recovery_email_template"):
            return f"file://{EMAIL_TEMPLATE_FILE_PATH}"

        return None

    @property
    def _smtp_connection_uri(self) -> str:
        smtp = self.smtp.get_relation_data()
        if not smtp:
            logger.info(
                "No smtp connection url found, the default placeholder value will be used. "
                "Use the smtp library to integrate with an email server"
            )
            # smtp_connection_uri is required to start the service, use a default value
            return "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"

        username = smtp.user
        server = smtp.host
        port = smtp.port
        transport_security = smtp.transport_security
        skip_ssl_verify = smtp.skip_ssl_verify
        password = (
            self.model.get_secret(id=smtp.password_id).get_content().get("password")
            if smtp.password_id
            else None
        )

        if transport_security == "none":
            return f"smtp://{username}:{password}@{server}:{port}/?disable_starttls=true"
        elif transport_security == "tls":
            method = "smtps"
        elif transport_security == "starttls":
            method = "smtp"

        if skip_ssl_verify:
            return f"{method}://{username}:{password}@{server}:{port}/?skip_ssl_verify=true"
        else:
            return f"{method}://{username}:{password}@{server}:{port}/"

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
        if self.model.relations[HYDRA_RELATION_NAME]:
            try:
                hydra_endpoints = self.hydra_endpoints.get_hydra_endpoints()
                oauth2_provider_url = hydra_endpoints["admin_endpoint"]
            except HydraEndpointsRelationDataMissingError:
                logger.info("No hydra-endpoint-info relation data found")
                return None

        return oauth2_provider_url

    def _get_registration_webhook_config(self) -> Optional[dict]:
        data = self.registration_webhook.consume_relation_data()
        return data if data else None

    def _get_login_ui_endpoint_info(self) -> Dict:
        return self.login_ui_endpoints.get_login_ui_endpoints() or {}

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
        for schema_file in IDENTITY_SCHEMAS_LOCAL_DIR_PATH.glob("*.json"):
            with open(schema_file) as f:
                schema = f.read()
            schemas[schema_file.stem] = schema
        return schemas

    def _get_default_identity_schema_config(self) -> Tuple[str, Dict]:
        schemas = self._get_default_identity_schemas()
        default_schema_id_file = IDENTITY_SCHEMAS_LOCAL_DIR_PATH / DEFAULT_SCHEMA_ID_FILE_NAME
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
        """Get the default schema id and the identity schemas.

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

    def _get_claims_mappers(self) -> Dict[str, str]:
        mappers = {}
        for file in MAPPERS_LOCAL_DIR_PATH.glob("*.jsonnet"):
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
            providers.extend([
                Provider.from_dict(provider) for provider in p[PROVIDERS_CONFIGMAP_FILE_NAME]
            ])
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
            "database_name": relation_data.get("database"),
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

    @run_after_config_updated
    def _restart_service(self) -> None:
        self._container.restart(WORKLOAD_CONTAINER_NAME)

    def _handle_status_update_config(self, event: HookEvent) -> None:
        if not self._container.can_connect():
            event.defer()
            logger.info("Cannot connect to Kratos container. Deferring event.")
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        if not self._validate_config_log_level():
            return

        self.unit.status = MaintenanceStatus("Configuring resources")

        if not self.model.relations[DB_RELATION_NAME]:
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

        if (
            self.model.relations[KRATOS_INFO_RELATION_NAME]
            or self.model.relations[KRATOS_EXTERNAL_IDP_INTEGRATOR_RELATION_NAME]
        ) and self.public_ingress.relation is None:
            self.unit.status = BlockedStatus(
                "Cannot send integration data without an external hostname. Please "
                "provide an ingress relation."
            )
            return
        elif (
            self.model.relations[KRATOS_INFO_RELATION_NAME]
            or self.model.relations[KRATOS_EXTERNAL_IDP_INTEGRATOR_RELATION_NAME]
        ) and self._public_url is None:
            self.unit.status = WaitingStatus("Waiting for ingress")
            event.defer()
            return

        if (
            self.config["enable_oidc_webauthn_sequencing"]
            and self.config["enable_passwordless_login_method"]
        ):
            self.unit.status = BlockedStatus(
                "OIDC-WebAuthn sequencing mode requires `enable_passwordless_login_method=False`. "
                "Please change the config."
            )
            return

        self._update_kratos_external_idp_configurations()
        self._cleanup_peer_data()
        self.cert_transfer.push_ca_certs()
        self._update_config()
        # We need to push the layer because this may run before _on_pebble_ready
        self._container.add_layer(WORKLOAD_CONTAINER_NAME, self._pebble_layer, combine=True)
        try:
            self._restart_service()
        except ChangeError as err:
            logger.error(str(err))
            self.unit.status = BlockedStatus(
                "Failed to restart the service, please check the logs"
            )
            return

        if template := self.config.get("recovery_email_template"):
            self._container.push(EMAIL_TEMPLATE_FILE_PATH, template, make_dirs=True)

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

        self._set_version()
        self._handle_status_update_config(event)

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        """Event Handler for config changed event."""
        self._handle_status_update_config(event)
        self._update_kratos_info_relation_data(event)

    def _on_remove(self, event: RemoveEvent) -> None:
        if not self.unit.is_leader():
            return

        config_map.delete_all()

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        logger.error(f"Failed to patch resource constraints: {event.message}")
        self.unit.status = BlockedStatus(event.message)

    def _get_tracing_endpoint_info(self) -> str:
        if not self._tracing_ready:
            return ""

        http_endpoint = urlparse(self.tracing.get_endpoint("otlp_http"))

        return http_endpoint.geturl().replace(f"{http_endpoint.scheme}://", "", 1) or ""  # type: ignore[arg-type]

    def _update_kratos_info_relation_data(self, event: RelationEvent) -> None:
        logger.info("Sending kratos info")

        (admin_endpoint, public_endpoint) = self._kratos_endpoints
        providers_configmap_name = self.providers_configmap.name
        schemas_configmap_name = self.schemas_configmap.name
        configmaps_namespace = self.model.name
        mfa_enabled = self.config.get("enforce_mfa")
        oidc_webauthn_sequencing_enabled = self.config.get("enable_oidc_webauthn_sequencing")

        if self._public_url is None:
            return

        self.info_provider.send_info_relation_data(
            admin_endpoint,
            public_endpoint,
            self._public_url,
            providers_configmap_name,
            schemas_configmap_name,
            configmaps_namespace,
            mfa_enabled,
            oidc_webauthn_sequencing_enabled,
        )

    def _patch_statefulset(self) -> None:
        if not self.unit.is_leader():
            return

        pod_spec_patch = {
            "containers": [
                {
                    "name": WORKLOAD_CONTAINER_NAME,
                    "volumeMounts": [
                        {
                            "mountPath": str(CONFIG_DIR_PATH),
                            "name": "config",
                            "readOnly": True,
                        },
                    ],
                },
            ],
            "volumes": [
                {
                    "name": "config",
                    "configMap": {"name": KRATOS_CONFIG_MAP_NAME},
                },
            ],
        }
        patch = {"spec": {"template": {"spec": pod_spec_patch}}}
        self.client.patch(StatefulSet, name=self.app.name, namespace=self.model.name, obj=patch)

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
            self._container.stop(WORKLOAD_CONTAINER_NAME)
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
        self._update_kratos_info_relation_data(event)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

        self._handle_status_update_config(event)
        self._update_kratos_info_relation_data(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

        self._handle_status_update_config(event)
        self._update_kratos_info_relation_data(event)

    def _update_kratos_external_idp_configurations(self) -> None:
        public_url = self._public_url
        if public_url is None:
            return

        for p in self.external_provider.get_providers():
            self.external_provider.set_relation_registered_provider(
                join(public_url, f"self-service/methods/oidc/callback/{p.provider_id}"),
                p.provider_id,
                p.relation_id,
            )

    def _on_client_config_changed(self, event: ClientConfigChangedEvent) -> None:
        self._handle_status_update_config(event)

    def _on_client_config_removed(self, event: ClientConfigRemovedEvent) -> None:
        self.unit.status = MaintenanceStatus("Removing external provider")
        self._handle_status_update_config(event)
        self.external_provider.remove_relation_registered_provider(event.relation_id)

    def _on_smtp_data_available(self, event: SmtpDataAvailableEvent):
        logger.info("Updating smtp mail courier configuration")
        self._handle_status_update_config(event)

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

    def _get_identity_id(self, event: ActionEvent) -> Optional[str]:
        identity_id = event.params.get("identity-id")
        email = event.params.get("email")
        if identity_id and email:
            event.fail("Only one of identity-id and email can be provided.")
            return None
        elif not identity_id and not email:
            event.fail("One of identity-id and email must be provided.")
            return None

        if email:
            identity = self.kratos.get_identity_from_email(email)
            if not identity:
                event.fail("Couldn't retrieve identity_id from email.")
                return None
            identity_id = identity["id"]

        return identity_id

    def _on_delete_identity_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = self._get_identity_id(event)

        event.log("Deleting the identity.")
        try:
            self.kratos.delete_identity(identity_id=identity_id)
        except Error as e:
            event.fail(f"Something went wrong when trying to run the command: {e}")
            return

        event.log(f"Successfully deleted the identity: {identity_id}.")
        event.set_results({"identity-id": identity_id})

    def _on_reset_password_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = self._get_identity_id(event)

        if secret_id := event.params.get("password-secret-id"):
            try:
                juju_secret = self.model.get_secret(id=secret_id)
                password = juju_secret.get_content().get("password")
            except SecretNotFoundError:
                event.fail("Secret not found")
                return
            except ModelError as err:
                event.fail(f"An error occurred: {err}")
                return

        event.log("Resetting password")

        try:
            if secret_id:
                ret = self.kratos.reset_password(identity_id=identity_id, password=password)
                event.log("Password changed successfully")
            else:
                ret = self.kratos.recover_password_with_code(identity_id=identity_id)
                event.log("Follow the link to reset the user's password")
        except requests.exceptions.RequestException as e:
            event.fail(f"Failed to request Kratos API: {e}")
            return

        event.set_results(dict_to_action_output(ret))

    def _on_invalidate_identity_sessions_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = self._get_identity_id(event)

        event.log("Invalidating user sessions")
        try:
            sessions_invalidated = self.kratos.invalidate_sessions(identity_id=identity_id)
            if not sessions_invalidated:
                event.log("User has no sessions")
                return
        except requests.exceptions.RequestException as e:
            event.fail(f"Failed to request Kratos API: {e}")
            return

        event.log("User sessions have been invalidated and deleted")

    def _on_reset_identity_mfa_action(self, event: ActionEvent) -> None:
        if not self._kratos_service_is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        mfa_type = event.params.get("mfa-type")
        identity_id = self._get_identity_id(event)

        if not mfa_type:
            event.fail("MFA type must be specified")
            return

        if mfa_type not in ("totp", "lookup_secret", "webauthn"):
            event.fail(
                f"Unsupported MFA credential type {mfa_type}, "
                "allowed methods are: `totp`, `lookup_secret` and `webauthn`"
            )
            return

        event.log("Resetting user's second authentication factor")
        try:
            credential_deleted = self.kratos.delete_mfa_credential(
                identity_id=identity_id, mfa_type=mfa_type
            )
            if not credential_deleted:
                event.log(f"User has no {mfa_type} credentials")
                return
        except requests.exceptions.RequestException as e:
            event.fail(f"Failed to request Kratos API: {e}")
            return

        event.log("Second authentication factor was reset")

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
        password = None
        if secret_id := event.params.get("password-secret-id"):
            try:
                juju_secret = self.model.get_secret(id=secret_id)
                password = juju_secret.get_content().get("password")
            except SecretNotFoundError:
                event.fail("Secret not found")
                return
            except ModelError as err:
                event.fail(f"An error occurred: {err}")
                return

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
            event.log("Creating recovery code for resetting admin password.")
            try:
                link = self.kratos.recover_password_with_code(identity_id)
            except requests.exceptions.RequestException as e:
                event.fail(f"Failed to request Kratos API: {e}")
                return
            res["password-reset-link"] = link["recovery_link"]
            res["password-reset-code"] = link["recovery_code"]
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

    def _configure_internal_ingress(self, event: HookEvent) -> None:
        """Method setting up the internal networking.

        Since :class:`TraefikRouteRequirer` may not have been constructed with an existing
        relation if a :class:`RelationJoinedEvent` comes through during the charm lifecycle, if we
        get one here, we should recreate it, but OF will give us grief about "two objects claiming
        to be ...", so manipulate its private `_relation` variable instead.

        Args:
            event: a :class:`HookEvent` to signal a change we may need to respond to.
        """
        if not self.unit.is_leader():
            return

        # If it's a RelationJoinedEvent, set it in the ingress object
        if isinstance(event, RelationJoinedEvent):
            self.internal_ingress._relation = event.relation

        # No matter what, check readiness -- this blindly checks whether `ingress._relation` is not
        # None, so it overlaps a little with the above, but works as expected on leader elections
        # and config-change
        if self.internal_ingress.is_ready():
            self.internal_ingress.submit_to_traefik(self._internal_ingress_config)
            self._update_kratos_info_relation_data(event)


if __name__ == "__main__":
    main(KratosCharm)
