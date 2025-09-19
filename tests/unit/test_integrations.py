# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from dataclasses import asdict
from unittest.mock import MagicMock, create_autospec, mock_open, patch

import pytest
from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificateTransferRequires,
)
from charms.data_platform_libs.v0.data_interfaces import DatabaseRequires
from charms.hydra.v0.hydra_endpoints import HydraEndpointsRequirer
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRequirer,
)
from charms.kratos.v0.kratos_registration_webhook import (
    KratosRegistrationWebhookRequirer,
    ProviderData,
)
from charms.kratos_external_idp_integrator.v1.kratos_external_provider import (
    BaseProvider,
    ExternalIdpRequirer,
)
from charms.smtp_integrator.v0.smtp import (
    AuthType,
    SmtpRelationData,
    SmtpRequires,
    TransportSecurity,
)
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from charms.traefik_k8s.v2.ingress import IngressPerAppRequirer
from yarl import URL

from constants import KRATOS_ADMIN_PORT, KRATOS_PUBLIC_PORT, POSTGRESQL_DSN_TEMPLATE
from integrations import (
    DatabaseConfig,
    ExternalIdpIntegratorData,
    HydraEndpointData,
    InternalIngressData,
    LoginUIEndpointData,
    PeerData,
    PublicIngressData,
    RegistrationWebhookData,
    SmtpData,
    TLSCertificates,
    TracingData,
)


class TestPeerData:
    @pytest.fixture
    def mocked_app(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mocked_model(self, mocked_app: MagicMock) -> MagicMock:
        model = MagicMock()
        model.app = mocked_app
        return model

    @pytest.fixture
    def peer_data(self, mocked_model: MagicMock) -> PeerData:
        return PeerData(mocked_model)

    @pytest.fixture
    def mocked_peer_integration_data(self, mocked_app: MagicMock, mocked_model: MagicMock) -> dict:
        peer_integration = MagicMock()
        peer_integration.data = {mocked_app: {}}
        mocked_model.get_relation.return_value = peer_integration
        return peer_integration.data[mocked_app]

    def test_get_with_existing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        mocked_peer_integration_data["key"] = '"val"'
        assert peer_data["key"] == "val"

    def test_get_with_missing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        assert not peer_data["missing"]

    def test_get_without_peer_integration(
        self, mocked_model: MagicMock, peer_data: PeerData
    ) -> None:
        mocked_model.get_relation.return_value = None
        assert not peer_data["key"]

    def test_set(self, mocked_peer_integration_data: dict, peer_data: PeerData) -> None:
        peer_data["key"] = "val"
        assert mocked_peer_integration_data["key"] == '"val"'

    def test_set_without_integration(
        self,
        mocked_model: MagicMock,
        mocked_peer_integration_data: dict,
        peer_data: PeerData,
    ) -> None:
        mocked_model.get_relation.return_value = None
        peer_data["key"] = "val"

        assert not mocked_peer_integration_data

    def test_pop_with_existing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        mocked_peer_integration_data["key"] = '"val"'

        actual = peer_data.pop("key")
        assert actual == "val"
        assert "key" not in mocked_peer_integration_data

    def test_pop_with_missing_key(
        self, mocked_peer_integration_data: dict, peer_data: PeerData
    ) -> None:
        assert not peer_data.pop("key")

    def test_pop_without_integration(
        self,
        mocked_model: MagicMock,
        mocked_peer_integration_data: dict,
        peer_data: PeerData,
    ) -> None:
        mocked_model.get_relation.return_value = None
        assert not peer_data.pop("key")

    def test_keys(self, mocked_peer_integration_data: dict, peer_data: PeerData) -> None:
        mocked_peer_integration_data.update({"x": "1", "y": "2"})
        assert list(peer_data.keys()) == ["x", "y"]

    def test_keys_without_integration(self, mocked_model: MagicMock, peer_data: PeerData) -> None:
        mocked_model.get_relation.return_value = None
        assert not peer_data.keys()


class TestDatabaseConfig:
    @pytest.fixture
    def database_config(self) -> DatabaseConfig:
        return DatabaseConfig(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
            migration_version="migration_version",
        )

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(DatabaseRequires)

    def test_dsn(self, database_config: DatabaseConfig) -> None:
        expected = POSTGRESQL_DSN_TEMPLATE.substitute(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
        )

        actual = database_config.dsn
        assert actual == expected

    def test_to_env_vars(self, database_config: DatabaseConfig) -> None:
        env_vars = database_config.to_env_vars()
        assert env_vars["DSN"] == database_config.dsn

    def test_load_with_integration(self, mocked_requirer: MagicMock) -> None:
        integration_id = 1
        mocked_requirer.relations = [MagicMock(id=integration_id)]
        mocked_requirer.database = "database"
        mocked_requirer.fetch_relation_data.return_value = {
            integration_id: {
                "endpoints": "endpoint",
                "username": "username",
                "password": "password",
            }
        }

        actual = DatabaseConfig.load(mocked_requirer)
        assert actual == DatabaseConfig(
            username="username",
            password="password",
            endpoint="endpoint",
            database="database",
            migration_version="migration_version_1",
        )

    def test_load_without_integration(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.database = "database"
        mocked_requirer.relations = []

        actual = DatabaseConfig.load(mocked_requirer)
        assert actual == DatabaseConfig()


class TestTracingData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(TracingEndpointRequirer)

    @pytest.mark.parametrize(
        "data, expected",
        [
            (TracingData(is_ready=False), {}),
            (
                TracingData(is_ready=True, http_endpoint="http_endpoint"),
                {
                    "TRACING_PROVIDER": "otel",
                    "TRACING_PROVIDERS_OTLP_SERVER_URL": "http_endpoint",
                    "TRACING_PROVIDERS_OTLP_INSECURE": "true",
                    "TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO": "1.0",
                },
            ),
        ],
    )
    def test_to_env_vars(self, data: TracingData, expected: dict) -> None:
        actual = data.to_env_vars()
        assert actual == expected

    def test_load_with_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = True
        mocked_requirer.get_endpoint.return_value = "http://http_endpoint"

        actual = TracingData.load(mocked_requirer)
        assert actual == TracingData(is_ready=True, http_endpoint="http_endpoint")

    def test_load_without_integration_ready(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = False

        actual = TracingData.load(mocked_requirer)
        assert actual == TracingData()


class TestLoginUIEndpointData:
    @pytest.fixture
    def endpoint_data(self) -> LoginUIEndpointData:
        return LoginUIEndpointData(
            login_url="login_url",
            error_url="error_url",
            settings_url="settings_url",
            recovery_url="recovery_url",
            webauthn_settings_url="webauthn_settings_url",
            registration_url="registration_url",
            consent_url="consent_url",
        )

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(LoginUIEndpointsRequirer)

    def test_to_service_configs(self, endpoint_data: LoginUIEndpointData) -> None:
        expected = {
            "default_browser_return_url": "login_url",
            "login_ui_url": "login_url",
            "error_ui_url": "error_url",
            "settings_ui_url": "settings_url",
            "recovery_ui_url": "recovery_url",
            "webauthn_settings_url": "webauthn_settings_url",
            "registration_ui_url": "registration_url",
        }
        actual = endpoint_data.to_service_configs()
        assert actual == expected

    def test_load(self, endpoint_data: LoginUIEndpointData, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_login_ui_endpoints.return_value = {
            "consent_url": "consent_url",
            "device_verification_url": "device_verification_url",
            "error_url": "error_url",
            "login_url": "login_url",
            "oidc_error_url": "oidc_error_url",
            "post_device_done_url": "post_device_done_url",
            "recovery_url": "recovery_url",
            "settings_url": "settings_url",
            "webauthn_settings_url": "webauthn_settings_url",
            "registration_url": "registration_url",
        }

        actual = LoginUIEndpointData.load(mocked_requirer)
        assert actual == endpoint_data

    def test_load_with_failure(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_login_ui_endpoints.side_effect = Exception

        actual = LoginUIEndpointData.load(mocked_requirer)
        assert actual == LoginUIEndpointData()


class TestHydraEndpointData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(HydraEndpointsRequirer)

    def test_to_env_vars(self) -> None:
        actual = HydraEndpointData(oauth2_provider_url="admin_endpoint").to_env_vars()
        assert actual == {"OAUTH2_PROVIDER_URL": "admin_endpoint"}

    def test_load(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_hydra_endpoints.return_value = {
            "public_endpoint": "public_endpoint",
            "admin_endpoint": "admin_endpoint",
        }

        actual = HydraEndpointData.load(mocked_requirer)
        assert actual == HydraEndpointData(oauth2_provider_url="admin_endpoint")

    def test_load_with_failure(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_hydra_endpoints.side_effect = Exception

        actual = HydraEndpointData.load(mocked_requirer)
        assert actual == HydraEndpointData()


class TestSmtpData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(SmtpRequires)

    @pytest.mark.parametrize(
        "transport_security,skip_ssl_verify,expected_uri",
        [
            (
                "tls",
                "true",
                "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true",
            ),
            (
                "none",
                "true",
                "smtp://test:test@mailslurper:1025/?disable_starttls=true",
            ),
            (
                "starttls",
                "true",
                "smtp://test:test@mailslurper:1025/?skip_ssl_verify=true",
            ),
            (
                "starttls",
                "false",
                "smtp://test:test@mailslurper:1025/",
            ),
        ],
    )
    def test_to_env_vars(
        self, transport_security: str, skip_ssl_verify: str, expected_uri: str
    ) -> None:
        data = SmtpData(transport_security=transport_security, skip_ssl_verify=skip_ssl_verify)
        env = data.to_env_vars()
        assert env["COURIER_SMTP_CONNECTION_URI"] == expected_uri

    def test_to_env_vars_defaults(self) -> None:
        data = SmtpData()
        env = data.to_env_vars()
        assert env["COURIER_SMTP_CONNECTION_URI"] == (
            "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"
        )

    def test_load(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_relation_data.return_value = SmtpRelationData(
            host="smtp.example.com",
            port=1025,
            user="user",
            password="password",
            transport_security=TransportSecurity.STARTTLS,
            auth_type=AuthType.NONE,
            skip_ssl_verify=True,
        )

        actual = SmtpData.load(mocked_requirer)
        assert actual == SmtpData(
            username="user",
            password="password",
            server="smtp.example.com",
            port=1025,
            transport_security="starttls",
            skip_ssl_verify="true",
        )


class TestPublicIngressData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(IngressPerAppRequirer)

    def test_to_service_configs(self) -> None:
        data = PublicIngressData(url=URL("https://example.com/some/path?foo=bar#frag"))
        actual = data.to_service_configs()

        assert actual == {"domain": "example.com", "origin": "https://example.com"}

    def test_to_env_vars(self) -> None:
        data = PublicIngressData(url=URL("https://example.com/some/path?foo=bar#frag"))
        env_vars = data.to_env_vars()

        assert env_vars["SERVE_PUBLIC_BASE_URL"] == "https://example.com/some/path?foo=bar#frag"
        allowed_urls = json.loads(env_vars["SELFSERVICE_ALLOWED_RETURN_URLS"])
        assert allowed_urls == ["https://example.com/"]

    def test_load(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.is_ready.return_value = True
        mocked_requirer.url = "https://example.com"

        data = PublicIngressData.load(mocked_requirer)
        assert str(data.url) == "https://example.com"


class TestInternalIngressData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        mocked = create_autospec(TraefikRouteRequirer)
        mocked._charm = MagicMock()
        mocked._charm.model.name = "model"
        mocked._charm.app.name = "app"
        mocked.scheme = "http"
        return mocked

    @pytest.fixture
    def ingress_template(self) -> str:
        return (
            '{"model": "{{ model }}", '
            '"app": "{{ app }}", '
            '"public_port": {{ public_port }}, '
            '"admin_port": {{ admin_port }}, '
            '"external_host": "{{ external_host }}"}'
        )

    def test_load_with_external_host(
        self, mocked_requirer: MagicMock, ingress_template: str
    ) -> None:
        mocked_requirer.external_host = "external.kratos.com"

        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = InternalIngressData.load(mocked_requirer)

        expected_ingress_config = {
            "model": "model",
            "app": "app",
            "public_port": KRATOS_PUBLIC_PORT,
            "admin_port": KRATOS_ADMIN_PORT,
            "external_host": "external.kratos.com",
        }
        assert actual == InternalIngressData(
            public_endpoint=URL("http://external.kratos.com/model-app"),
            admin_endpoint=URL("http://external.kratos.com/model-app"),
            config=expected_ingress_config,
        )

    def test_load_without_external_host(
        self, mocked_requirer: MagicMock, ingress_template: str
    ) -> None:
        mocked_requirer.external_host = ""

        with patch("builtins.open", mock_open(read_data=ingress_template)):
            actual = InternalIngressData.load(mocked_requirer)

        expected_ingress_config = {
            "model": "model",
            "app": "app",
            "public_port": KRATOS_PUBLIC_PORT,
            "admin_port": KRATOS_ADMIN_PORT,
            "external_host": "",
        }
        assert actual == InternalIngressData(
            public_endpoint=URL(f"http://app.model.svc.cluster.local:{KRATOS_PUBLIC_PORT}"),
            admin_endpoint=URL(f"http://app.model.svc.cluster.local:{KRATOS_ADMIN_PORT}"),
            config=expected_ingress_config,
        )


class TestRegistrationWebhookData:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(KratosRegistrationWebhookRequirer)

    def test_to_service_configs(self) -> None:
        data = RegistrationWebhookData(url="http://hook", method="POST", is_ready=True)
        configs = data.to_service_configs()

        assert configs == {"registration_webhook_config": asdict(data)}

    def test_load(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.consume_relation_data.return_value = ProviderData(
            url="http://webhook",
            body='{"foo":"bar"}',
            method="POST",
            response_ignore=True,
            response_parse=False,
            auth_type="bearer",
            auth_config_name="Authorization",
            auth_config_in="header",
            auth_config_value="token",
        )

        data = RegistrationWebhookData.load(mocked_requirer)
        assert data == RegistrationWebhookData(
            url="http://webhook",
            body='{"foo":"bar"}',
            method="POST",
            response_ignore=True,
            response_parse=False,
            auth_enabled=True,
            auth_type="bearer",
            auth_config_name="Authorization",
            auth_config_in="header",
            auth_config_value="token",
            is_ready=True,
        )


class TestExternalIdpIntegrationData:
    @pytest.fixture
    def mocked_providers(self) -> list[BaseProvider]:
        providers = [
            {"provider": "google", "client_id": "cid", "issuer": "https://accounts.google.com"},
            {"provider": "github", "client_id": "cid2", "issuer": "https://github.com"},
        ]

        return [BaseProvider.model_validate(provider) for provider in providers]

    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(ExternalIdpRequirer)

    def test_to_service_configs(self, mocked_providers: list[BaseProvider]) -> None:
        data = ExternalIdpIntegratorData(ext_idp_providers=mocked_providers)

        configs = data.to_service_configs()
        assert configs == {"external_oidc_providers": mocked_providers}

    def test_load(self, mocked_requirer: MagicMock, mocked_providers: list[BaseProvider]) -> None:
        mocked_requirer.get_providers.return_value = mocked_providers

        data = ExternalIdpIntegratorData.load(mocked_requirer)
        assert data.ext_idp_providers == mocked_providers


class TestTLSCertificates:
    @pytest.fixture
    def mocked_requirer(self) -> MagicMock:
        return create_autospec(CertificateTransferRequires)

    def test_load(self, mocked_requirer: MagicMock) -> None:
        mocked_requirer.get_all_certificates.return_value = {"ca_cert1", "ca_cert2"}

        certificates = TLSCertificates.load(mocked_requirer)

        assert set(certificates.ca_bundle.splitlines()) == {"ca_cert1", "ca_cert2"}
