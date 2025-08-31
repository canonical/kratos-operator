# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Dict, Generator, Tuple
from unittest.mock import MagicMock

import pytest
from ops.model import Container
from ops.pebble import ExecError
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import KratosCharm
from constants import WORKLOAD_CONTAINER
from kratos import KratosAPI


@pytest.fixture()
def harness(
    mocked_kubernetes_service_patcher: MagicMock,
) -> Harness:
    harness = Harness(KratosCharm)
    harness.set_model_name("kratos-model")
    harness.set_can_connect("kratos", True)
    harness.set_leader(True)
    harness.begin()
    harness.add_network("10.0.0.10")
    return harness


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


@pytest.fixture(autouse=True)
def lk_client(mocker: MockerFixture) -> None:
    mock_lightkube = mocker.patch("charm.Client", autospec=True)
    return mock_lightkube.return_value


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
def password_secret(harness: Harness) -> Tuple[str, str]:
    user_password = "user_password"
    secret = harness.add_user_secret({"password": user_password})
    harness.grant_secret(secret, harness.charm.app)
    return user_password, secret
