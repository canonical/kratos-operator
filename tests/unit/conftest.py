# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, PropertyMock, create_autospec

import pytest
from ops import testing
from ops.model import Container, Unit
from pytest_mock import MockerFixture

from constants import COOKIE_SECRET_CONTENT_KEY, COOKIE_SECRET_LABEL


@pytest.fixture(autouse=True)
def mocked_k8s_resource_patch(mocker: MockerFixture) -> None:
    mocker.patch(
        "charms.observability_libs.v0.kubernetes_compute_resources_patch.ResourcePatcher",
        autospec=True,
    )
    mocker.patch.multiple(
        "charm.KubernetesComputeResourcesPatch",
        _namespace="kratos-model",
        _patch=lambda *a, **kw: True,
        is_ready=lambda *a, **kw: True,
    )


@pytest.fixture
def mocked_container() -> MagicMock:
    return create_autospec(Container)


@pytest.fixture
def mocked_unit(mocked_container: MagicMock) -> MagicMock:
    mocked = create_autospec(Unit)
    mocked.get_container.return_value = mocked_container
    return mocked


@pytest.fixture
def mocked_charm_holistic_handler(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.KratosCharm._holistic_handler")


@pytest.fixture
def mocked_create_configmaps(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.create_configmaps")


@pytest.fixture
def mocked_remove_configmaps(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.remove_configmaps")


@pytest.fixture
def mocked_workload_service(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.WorkloadService", autospec=True)


@pytest.fixture
def mocked_workload_service_version(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.WorkloadService.version", new_callable=PropertyMock, return_value="1.0.0"
    )


@pytest.fixture
def mocked_workload_service_running(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.WorkloadService.is_running", new_callable=PropertyMock, return_value=True
    )


@pytest.fixture
def mocked_migration_needed(mocker: MockerFixture) -> MagicMock:
    return mocker.patch(
        "charm.KratosCharm.migration_needed", new_callable=PropertyMock, return_value=True
    )


@pytest.fixture
def charm_secret() -> testing.Secret:
    return testing.Secret(
        label=COOKIE_SECRET_LABEL, tracked_content={COOKIE_SECRET_CONTENT_KEY: "cookie"}
    )


@pytest.fixture
def peer_integration() -> testing.Relation:
    return testing.PeerRelation(
        endpoint="kratos-peers",
        interface="kratos-peers",
    )


@pytest.fixture
def database_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="pg-database",
        interface="postgresql_client",
        remote_app_name="postgresql-k8s",
        remote_app_data={
            "data": '{"database": "kratos", "extra-user-roles": "SUPERUSER"}',
            "database": "database",
            "endpoints": "endpoints",
            "username": "username",
            "password": "password",
        },
    )


@pytest.fixture
def registration_webhook_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="kratos-registration-webhook",
        interface="kratos_registration_webhook",
        remote_app_name="user-verification-service",
        remote_app_data={
            "url": "url",
            "body": "body",
            "method": "method",
        },
    )


@pytest.fixture
def public_ingress_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="public-ingress",
        interface="ingress",
        remote_app_name="traefik-public",
        remote_app_data={"ingress": '{"url": "https://public.example.com"}'},
    )


@pytest.fixture
def admin_ingress_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="admin-ingress",
        interface="ingress",
        remote_app_name="traefik-admin",
        remote_app_data={"ingress": '{"url": "https://admin.example.com"}'},
    )


@pytest.fixture
def internal_ingress_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="internal-ingress",
        interface="traefik-route",
        remote_app_name="traefik-internal",
        remote_app_data={"external_host": "example.com", "scheme": "https"},
    )


@pytest.fixture
def external_idp_integrator_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="kratos-external-idp",
        interface="external_provider",
        remote_app_name="kratos-external-idp-integrator",
        remote_app_data={
            "providers": '[{"client_id": "client_id", "provider": "generic", "client_secret": "client_secret", "issuer_url": ""}]',
        },
    )


@pytest.fixture
def smtp_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="smtp",
        interface="smtp",
        remote_app_name="smtp-integrator",
        remote_app_data={
            "user": "user",
            "password": "password",
            "host": "host",
            "port": "1025",
            "auth_type": "none",
            "transport_security": "none",
        },
    )


@pytest.fixture
def certificate_transfer_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="receive-ca-cert",
        interface="certificate_transfer",
        remote_app_name="self-signed-certificates",
    )


@pytest.fixture
def kratos_info_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="kratos-info",
        interface="kratos_info",
        remote_app_name="identity-platform-login-ui",
    )


@pytest.fixture
def hydra_endpoint_info_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="hydra-endpoint-info",
        interface="hydra_endpoints",
        remote_app_name="hydra",
        remote_app_data={"admin_endpoint": "admin_endpoint", "public_endpoint": "public_endpoint"},
    )


@pytest.fixture
def tracing_integration() -> testing.Relation:
    return testing.Relation(
        endpoint="tracing",
        interface="tracing",
        remote_app_name="tempo-coordinator-k8s",
    )
