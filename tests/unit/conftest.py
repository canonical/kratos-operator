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
def mocked_hook_event(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("ops.charm.HookEvent", autospec=True)


@pytest.fixture()
def mocked_kratos_process() -> MagicMock:
    mock = MagicMock()
    mock.wait_output.return_value = (json.dumps({"identity_id": 1234}), None)
    return mock


@pytest.fixture()
def kratos_api(mocked_kratos_process: MagicMock) -> KratosAPI:
    container = MagicMock()
    container.exec = MagicMock(return_value=mocked_kratos_process)
    return KratosAPI("http://localhost:4434", container)


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker: MockerFixture) -> MagicMock:
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    return mocked_service_patcher


@pytest.fixture()
def mocked_kratos_service(harness: Harness, mocked_container: MagicMock) -> Generator:
    service = MagicMock()
    service.is_running = lambda: True
    mocked_container.get_service = MagicMock(return_value=service)
    mocked_container.can_connect = MagicMock(return_value=True)
    return service


@pytest.fixture()
def mocked_fqdn(mocker: MockerFixture) -> MagicMock:
    mocked_fqdn = mocker.patch("socket.getfqdn")
    mocked_fqdn.return_value = "kratos"
    return mocked_fqdn


@pytest.fixture()
def mocked_container(harness: Harness, mocker: MockerFixture) -> Container:
    container = harness.model.unit.get_container("kratos")
    setattr(container, "restart", mocker.MagicMock())
    setattr(container, "start", mocker.MagicMock())
    setattr(container, "replan", mocker.MagicMock())
    return container


@pytest.fixture()
def mocked_pebble_exec(mocker: MockerFixture) -> MagicMock:
    mocked_pebble_exec = mocker.patch("ops.model.Container.exec")
    return mocked_pebble_exec


@pytest.fixture()
def mocked_pebble_exec_success(mocker: MockerFixture, mocked_pebble_exec: MagicMock) -> MagicMock:
    mocked_process = mocker.patch("ops.pebble.ExecProcess")
    mocked_process.wait_output.return_value = ("Success", None)
    mocked_pebble_exec.return_value = mocked_process
    return mocked_pebble_exec


@pytest.fixture()
def mocked_pebble_exec_failed(mocked_pebble_exec: MagicMock) -> MagicMock:
    mocked_pebble_exec.side_effect = ExecError(
        exit_code=400, stderr="Failed to execute", stdout="Failed", command=["test", "command"]
    )
    return mocked_pebble_exec


@pytest.fixture(autouse=True)
def mocked_restart_service(mocker: MockerFixture) -> MagicMock:
    def restart_service(self, restart: bool = False) -> None:
        if restart:
            self._container.restart(WORKLOAD_CONTAINER)
        elif not self._container.get_service(WORKLOAD_CONTAINER).is_running():
            self._container.start(WORKLOAD_CONTAINER)
        else:
            self._container.replan()

    return mocker.patch(
        "charm.KratosCharm._restart_service",
        restart_service,
    )


@pytest.fixture()
def kratos_identity_json() -> Dict:
    return {
        "created_at": "2023-03-31T14:04:49.667264Z",
        "credentials": {
            "password": {
                "created_at": "2023-03-31T14:04:49.667718Z",
                "identifiers": ["admin"],
                "type": "password",
                "updated_at": "2023-03-31T14:04:49.667718Z",
                "version": 0,
            }
        },
        "id": "5be8ea62-1c64-4a28-ac0c-7dd7d9cf7d05",
        "schema_id": "admin",
        "schema_url": "http://localhost:4433/schemas/YWRtaW4",
        "state": "active",
        "state_changed_at": "2023-03-31T14:04:49.666623636Z",
        "traits": {
            "email": "aa@bb.com",
            "name": "Joe Doe",
            "phone_number": "+306912345678",
            "username": "admin",
        },
        "updated_at": "2023-03-31T14:04:49.667264Z",
        "verifiable_addresses": [
            {
                "created_at": "2023-03-31T14:04:49.667503Z",
                "id": "02321296-6069-483f-b17a-9889fdae722f",
                "status": "pending",
                "updated_at": "2023-03-31T14:04:49.667503Z",
                "value": "aa@bb.com",
                "verified": False,
                "via": "email",
            }
        ],
    }


@pytest.fixture()
def mocked_migration_is_needed(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.KratosCharm._migration_is_needed", return_value=False)


@pytest.fixture()
def mocked_get_secret(mocker: MockerFixture) -> MagicMock:
    return mocker.patch("charm.KratosCharm._get_secret", return_value={"cookie": "secret"})


@pytest.fixture(autouse=True)
def mocked_get_version(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.get_version", return_value=None)
    mock.return_value = "1.0.1"
    return mock


@pytest.fixture(autouse=True)
def mocked_push_ca_certs(mocker: MockerFixture):
    mock = mocker.patch(
        "certificate_transfer_integration.CertTransfer.push_ca_certs", return_value=None
    )
    return mock


@pytest.fixture()
def mocked_recovery_email_template(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch(
        "charm.KratosCharm._recovery_email_template",
        return_value="file:///etc/config/templates/recovery-body.html.gotmpl",
    )
    return mock


@pytest.fixture()
def mocked_get_identity(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.get_identity", return_value=kratos_identity_json)
    return mock


@pytest.fixture()
def mocked_delete_identity(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.delete_identity", return_value=kratos_identity_json["id"])
    return mock


@pytest.fixture()
def mocked_get_identity_from_email(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch(
        "charm.KratosAPI.get_identity_from_email", return_value=kratos_identity_json
    )
    return mock


@pytest.fixture()
def recover_password_with_code_resp() -> Dict:
    return {
        "recovery_link": "http://kratos-ui/recovery?flow=2ebd739f-7c9c-404e-8ec9-769c055f5393",
        "recovery_code": "123456",
        "expires_at": "2023-04-03T21:47:52.869721347Z",
    }


@pytest.fixture()
def mocked_recover_password_with_code(
    mocker: MockerFixture, recover_password_with_code_resp: Dict
) -> MagicMock:
    mock = mocker.patch(
        "charm.KratosAPI.recover_password_with_code", return_value=recover_password_with_code_resp
    )
    return mock


@pytest.fixture()
def mocked_reset_password(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.reset_password", return_value=kratos_identity_json)
    return mock


@pytest.fixture()
def mocked_invalidate_sessions(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.invalidate_sessions", return_value=True)
    return mock


@pytest.fixture()
def mocked_delete_mfa_credential(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.delete_mfa_credential", return_value=True)
    return mock


@pytest.fixture()
def mocked_list_oidc_identifiers(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.list_oidc_identifiers", return_value=["some-idp:123456"])
    return mock


@pytest.fixture()
def mocked_delete_oidc_credential(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.delete_oidc_credential", return_value=True)
    return mock


@pytest.fixture()
def mocked_create_identity(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.create_identity", return_value=kratos_identity_json)
    return mock


@pytest.fixture()
def mocked_run_migration(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.run_migration", return_value=(None, None))
    return mock


@pytest.fixture(autouse=True)
def mocked_kratos_configmap(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.KratosConfigMap", autospec=True)
    return mock.return_value


@pytest.fixture(autouse=True)
def mocked_schemas_configmap(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.IdentitySchemaConfigMap", autospec=True)
    mock.return_value.get.return_value = {}
    mock.return_value.name = "identity-schemas"
    return mock.return_value


@pytest.fixture(autouse=True)
def mocked_providers_configmap(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.ProvidersConfigMap", autospec=True)
    mock.return_value.name = "providers"
    return mock.return_value


@pytest.fixture()
def mocked_push_default_files(mocker: MockerFixture) -> MagicMock:
    mocked = mocker.patch("charm.KratosCharm._push_default_files")
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
