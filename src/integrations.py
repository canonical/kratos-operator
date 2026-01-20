# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
import subprocess
from dataclasses import asdict, dataclass, field
from typing import Any, KeysView, Optional, Type, TypeAlias, Union
from urllib.parse import urlparse

import dacite
from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hydra.v0.hydra_endpoints import HydraEndpointsRequirer
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRequirer,
)
from charms.kratos.v0.kratos_registration_webhook import KratosRegistrationWebhookRequirer
from charms.kratos_external_idp_integrator.v1.kratos_external_provider import ExternalIdpRequirer
from charms.smtp_integrator.v0.smtp import SmtpRequires
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from jinja2 import Template
from ops import Model
from typing_extensions import Self
from yarl import URL

from configs import ServiceConfigs
from constants import (
    CA_BUNDLE_PATH,
    INTEGRATION_CA_BUNDLE_PATH,
    INTERNAL_ROUTE_INTEGRATION_NAME,
    KRATOS_ADMIN_PORT,
    KRATOS_PUBLIC_PORT,
    PEER_INTEGRATION_NAME,
    POSTGRESQL_DSN_TEMPLATE,
    PUBLIC_ROUTE_INTEGRATION_NAME,
)
from env_vars import EnvVars

logger = logging.getLogger(__name__)

JsonSerializable: TypeAlias = Union[dict[str, Any], list[Any], int, str, float, bool, Type[None]]


class PeerData:
    def __init__(self, model: Model) -> None:
        self._model = model
        self._app = model.app

    def __getitem__(self, key: str) -> JsonSerializable:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        value = peers.data[self._app].get(key)
        return json.loads(value) if value else {}

    def __setitem__(self, key: str, value: Any) -> None:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return

        peers.data[self._app][key] = json.dumps(value)

    def pop(self, key: str) -> JsonSerializable:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return {}

        data = peers.data[self._app].pop(key, None)
        return json.loads(data) if data else {}

    def keys(self) -> KeysView[str]:
        if not (peers := self._model.get_relation(PEER_INTEGRATION_NAME)):
            return KeysView({})

        return peers.data[self._app].keys()


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """The data source from the database integration."""

    endpoint: str = ""
    database: str = ""
    username: str = ""
    password: str = ""
    migration_version: str = ""

    @property
    def dsn(self) -> str:
        return POSTGRESQL_DSN_TEMPLATE.substitute(
            username=self.username,
            password=self.password,
            endpoint=self.endpoint,
            database=self.database,
        )

    def to_env_vars(self) -> EnvVars:
        return {
            "DSN": self.dsn,
        }

    @classmethod
    def load(cls, requirer: DatabaseRequires) -> Self:
        if not (database_integrations := requirer.relations):
            return cls()

        integration_id = database_integrations[0].id
        integration_data: dict[str, str] = requirer.fetch_relation_data()[integration_id]

        return cls(
            endpoint=integration_data.get("endpoints", "").split(",")[0],
            database=requirer.database,
            username=integration_data.get("username", ""),
            password=integration_data.get("password", ""),
            migration_version=f"migration_version_{integration_id}",
        )


@dataclass(frozen=True, slots=True)
class TracingData:
    """The data source from the tracing integration."""

    is_ready: bool = False
    http_endpoint: str = ""

    def to_env_vars(self) -> EnvVars:
        if not self.is_ready:
            return {}

        return {
            "TRACING_PROVIDER": "otel",
            "TRACING_PROVIDERS_OTLP_SERVER_URL": self.http_endpoint,
            "TRACING_PROVIDERS_OTLP_INSECURE": "true",
            "TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO": "1.0",
        }

    @classmethod
    def load(cls, requirer: TracingEndpointRequirer) -> Self:
        if not (is_ready := requirer.is_ready()):
            return cls()

        http_endpoint = urlparse(requirer.get_endpoint("otlp_http"))

        return cls(
            is_ready=is_ready,
            http_endpoint=http_endpoint.geturl().replace(f"{http_endpoint.scheme}://", "", 1),  # type: ignore
        )


@dataclass(frozen=True, slots=True)
class LoginUIEndpointData:
    """The data source from the login-ui integration."""

    login_url: str = ""
    error_url: str = ""
    settings_url: str = ""
    recovery_url: str = ""
    verification_url: str = ""
    webauthn_settings_url: str = ""
    account_linking_settings_url: str = ""
    registration_url: str = ""
    consent_url: str = ""

    def is_ready(self) -> bool:
        return all(v for _, v in self.to_service_configs().items())

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "default_browser_return_url": self.login_url,
            "login_ui_url": self.login_url,
            "error_ui_url": self.error_url,
            "settings_ui_url": self.settings_url,
            "recovery_ui_url": self.recovery_url,
            "verification_ui_url": self.verification_url,
            "webauthn_settings_url": self.webauthn_settings_url,
            "account_linking_settings_url": self.account_linking_settings_url,
            "registration_ui_url": self.registration_url,
        }

    @classmethod
    def load(cls, requirer: LoginUIEndpointsRequirer) -> Self:
        try:
            login_ui_endpoints = requirer.get_login_ui_endpoints()
        except Exception as exc:
            logger.error("Failed to fetch the login ui endpoints: %s", exc)
            return cls()

        return (
            dacite.from_dict(data_class=LoginUIEndpointData, data=login_ui_endpoints)
            if login_ui_endpoints
            else cls()
        )


@dataclass(frozen=True, slots=True)
class HydraEndpointData:
    """The data source from the login-ui integration."""

    oauth2_provider_url: str = ""

    def to_env_vars(self) -> EnvVars:
        if not self.oauth2_provider_url:
            return {}

        return {
            "OAUTH2_PROVIDER_URL": self.oauth2_provider_url,
        }

    @classmethod
    def load(cls, requirer: HydraEndpointsRequirer) -> Self:
        try:
            hydra_endpoints = requirer.get_hydra_endpoints()
        except Exception as exc:
            logger.error("Failed to fetch the hydra endpoints: %s", exc)
            return cls()

        return (
            cls(oauth2_provider_url=hydra_endpoints["admin_endpoint"])
            if hydra_endpoints
            else cls()
        )


@dataclass(frozen=True, slots=True)
class SmtpData:
    """The data source from the smtp integration."""

    username: str = "test"
    password: str = "test"
    server: str = "mailslurper"
    port: int = 1025
    transport_security: str = "tls"
    skip_ssl_verify: str = "true"

    def to_env_vars(self) -> EnvVars:
        scheme, option = "", ""

        if self.skip_ssl_verify == "true":
            option = "?skip_ssl_verify=true"

        if self.transport_security == "none":
            scheme = "smtp"
            option = "?disable_starttls=true"

        if self.transport_security == "tls":
            scheme = "smtps"

        if self.transport_security == "starttls":
            scheme = "smtp"

        return {
            "COURIER_SMTP_CONNECTION_URI": f"{scheme}://{self.username}:{self.password}@{self.server}:{self.port}/{option}",
            "COURIER_SMTP_FROM_ADDRESS": "identity@canonical.com",
            "COURIER_SMTP_FROM_NAME": "Canonical Identity Platform",
        }

    @classmethod
    def load(cls, requirer: SmtpRequires) -> Self:
        if not (smtp_data := requirer.get_relation_data()):
            return cls()

        return cls(
            username=smtp_data.user or "test",
            password=smtp_data.password or "test",
            server=smtp_data.host,
            port=smtp_data.port,
            transport_security=smtp_data.transport_security,
            skip_ssl_verify="true" if smtp_data.skip_ssl_verify else "false",
        )


@dataclass(frozen=True, slots=True)
class PublicRouteData:
    """The data source from the public-route integration."""

    url: URL = URL()
    config: dict = field(default_factory=dict)

    @classmethod
    def _external_host(cls, requirer: TraefikRouteRequirer) -> str:
        if not (relation := requirer._charm.model.get_relation(PUBLIC_ROUTE_INTEGRATION_NAME)):
            return
        if not relation.app:
            return
        return relation.data[relation.app].get("external_host", "")

    @classmethod
    def _scheme(cls, requirer: TraefikRouteRequirer) -> str:
        if not (relation := requirer._charm.model.get_relation(PUBLIC_ROUTE_INTEGRATION_NAME)):
            return
        if not relation.app:
            return
        return relation.data[relation.app].get("scheme", "")

    @classmethod
    def load(cls, requirer: TraefikRouteRequirer) -> "PublicRouteData":
        model, app = requirer._charm.model.name, requirer._charm.app.name
        external_host = cls._external_host(requirer)
        scheme = cls._scheme(requirer)

        external_endpoint = f"{scheme}://{external_host}"

        # template could have use PathPrefixRegexp but going for a simple one right now
        with open("templates/public-route.j2", "r") as file:
            template = Template(file.read())

        ingress_config = json.loads(
            template.render(
                model=model,
                app=app,
                public_port=KRATOS_PUBLIC_PORT,
                external_host=external_host,
            )
        )

        if not external_host:
            logger.error("External hostname is not set on the ingress provider")
            return cls()

        return cls(
            url=URL(external_endpoint),
            config=ingress_config,
        )

    @property
    def secured(self) -> bool:
        return self.url.scheme == "https"

    def to_service_configs(self) -> ServiceConfigs:
        return (
            {"domain": self.url.host, "origin": f"{self.url.scheme}://{self.url.host}"}
            if self.url
            else {}
        )

    def to_env_vars(self) -> EnvVars:
        return (
            {
                "SERVE_PUBLIC_BASE_URL": str(self.url),
                "SELFSERVICE_ALLOWED_RETURN_URLS": json.dumps(
                    [
                        str(
                            self.url
                            .with_path("")
                            .without_query_params()
                            .with_fragment(None)
                            .with_path("/")
                        )
                    ],
                ),
            }
            if self.url
            else {}
        )


@dataclass(frozen=True, slots=True)
class InternalRouteData:
    """The data source from the internal-ingress integration."""

    public_endpoint: URL
    admin_endpoint: URL
    config: dict = field(default_factory=dict)

    @classmethod
    def _external_host(cls, requirer: TraefikRouteRequirer) -> str:
        if not (relation := requirer._charm.model.get_relation(INTERNAL_ROUTE_INTEGRATION_NAME)):
            return
        if not relation.app:
            return
        return relation.data[relation.app].get("external_host", "")

    @classmethod
    def _scheme(cls, requirer: TraefikRouteRequirer) -> str:
        if not (relation := requirer._charm.model.get_relation(INTERNAL_ROUTE_INTEGRATION_NAME)):
            return
        if not relation.app:
            return
        return relation.data[relation.app].get("scheme", "")

    @classmethod
    def load(cls, requirer: TraefikRouteRequirer) -> "InternalRouteData":
        model, app = requirer._charm.model.name, requirer._charm.app.name
        external_host = cls._external_host(requirer)
        scheme = cls._scheme(requirer) or "http"

        external_endpoint = f"{scheme}://{external_host}"

        with open("templates/internal-route.j2", "r") as file:
            template = Template(file.read())

        ingress_config = json.loads(
            template.render(
                model=model,
                app=app,
                public_port=KRATOS_PUBLIC_PORT,
                admin_port=KRATOS_ADMIN_PORT,
                external_host=external_host,
            )
        )

        public_endpoint = URL(
            external_endpoint
            if external_host
            else f"{scheme}://{app}.{model}.svc.cluster.local:{KRATOS_PUBLIC_PORT}"
        )
        admin_endpoint = URL(
            external_endpoint
            if external_host
            else f"{scheme}://{app}.{model}.svc.cluster.local:{KRATOS_ADMIN_PORT}"
        )

        return cls(
            public_endpoint=public_endpoint,
            admin_endpoint=admin_endpoint,
            config=ingress_config,
        )


@dataclass(frozen=True, slots=True)
class RegistrationWebhookData:
    """The data source from the kratos-registration-webhook integration."""

    url: str = ""
    body: str = ""
    method: str = ""
    emit_analytics_event: bool = False
    response_ignore: bool = False
    response_parse: bool = False
    auth_enabled: bool = True
    auth_type: str = "api_key"
    auth_config_name: str = "Authorization"
    auth_config_value: Optional[str] = None
    auth_config_in: str = "header"
    is_ready: bool = False

    def to_service_configs(self) -> ServiceConfigs:
        return {"registration_webhook_config": asdict(self)} if self.is_ready else {}

    @classmethod
    def load(cls, requirer: KratosRegistrationWebhookRequirer) -> Self:
        webhook_data = requirer.consume_relation_data()
        if not webhook_data:
            return cls()

        return cls(
            url=webhook_data.url,
            body=webhook_data.body,
            method=webhook_data.method,
            response_ignore=webhook_data.response_ignore,
            response_parse=webhook_data.response_parse,
            auth_enabled=webhook_data.auth_enabled,
            auth_type=webhook_data.auth_type,
            auth_config_name=webhook_data.auth_config_name,  # type: ignore
            auth_config_value=webhook_data.auth_config_value,
            auth_config_in=webhook_data.auth_config_in,  # type: ignore
            is_ready=True,
        )


@dataclass(frozen=True, slots=True)
class ExternalIdpIntegratorData:
    ext_idp_providers: list = field(default_factory=list)

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "external_oidc_providers": self.ext_idp_providers,
        }

    @classmethod
    def load(cls, requirer: ExternalIdpRequirer) -> Self:
        return cls(ext_idp_providers=requirer.get_providers())


@dataclass(frozen=True, slots=True)
class TLSCertificates:
    ca_bundle: str

    @classmethod
    def load(cls, requirer: CertificateTransferRequires) -> Self:
        """Fetch the CA certificates from all "receive-ca-cert" integrations.

        Compose the trusted CA certificates in /etc/ssl/certs/ca-certificates.crt.
        """
        ca_certs = requirer.get_all_certificates()
        ca_bundle = "\n".join(sorted(ca_certs))

        if ca_bundle:
            current_ca_cert = (
                INTEGRATION_CA_BUNDLE_PATH.read_text()
                if INTEGRATION_CA_BUNDLE_PATH.exists()
                else ""
            )
            if current_ca_cert != ca_bundle:
                INTEGRATION_CA_BUNDLE_PATH.parent.mkdir(parents=True, exist_ok=True)
                INTEGRATION_CA_BUNDLE_PATH.write_text(ca_bundle)
                subprocess.run(["update-ca-certificates", "--fresh"], check=True)
        else:
            if INTEGRATION_CA_BUNDLE_PATH.exists():
                INTEGRATION_CA_BUNDLE_PATH.unlink(missing_ok=True)
                subprocess.run(["update-ca-certificates", "--fresh"], check=True)

        return cls(ca_bundle=CA_BUNDLE_PATH.read_text())
