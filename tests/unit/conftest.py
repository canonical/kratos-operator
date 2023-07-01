# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Dict, Generator
from unittest.mock import MagicMock

import pytest
from ops.model import Container
from ops.pebble import ExecError
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import KratosCharm
from kratos import KratosAPI


@pytest.fixture()
def harness(mocked_kubernetes_service_patcher: MagicMock) -> Harness:
    harness = Harness(KratosCharm)
    harness.set_model_name("kratos-model")
    harness.set_can_connect("kratos", True)
    harness.set_leader(True)
    harness.begin()
    return harness


@pytest.fixture()
def mocked_kratos_process() -> MagicMock:
    mock = MagicMock()
    mock.wait_output.return_value = (json.dumps(dict(identity_id=1234)), None)
    return mock


@pytest.fixture()
def kratos_api(mocked_kratos_process: MagicMock) -> KratosAPI:
    container = MagicMock()
    container.exec = MagicMock(return_value=mocked_kratos_process)
    return KratosAPI("http://localhost:4434", container, "/etc/config/kratos.yaml")


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
def mocked_get_identity(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.get_identity", return_value=kratos_identity_json)
    return mock


@pytest.fixture()
def mocked_delete_identity(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.delete_identity", return_value=kratos_identity_json["id"])
    return mock


@pytest.fixture()
def mocked_list_identity(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.list_identities", return_value=[kratos_identity_json])
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
def recover_password_with_link_resp() -> Dict:
    return {
        "recovery_link": "http://kratos-ui/self-service/recovery?flow=e18560f9-8f50-4679-bcc9-d6cea2bb203f&token=5UJ9GgQTxvSp53zkwgOkjG9eRvnYjEYq",
        "expires_at": "2023-04-03T21:47:52.869721347Z",
    }


@pytest.fixture()
def mocked_recover_password_with_link(
    mocker: MockerFixture, recover_password_with_link_resp: Dict
) -> MagicMock:
    mock = mocker.patch(
        "charm.KratosAPI.recover_password_with_link", return_value=recover_password_with_link_resp
    )
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
def mocked_log_proxy_consumer_setup_promtail(mocker: MockerFixture) -> MagicMock:
    mocked_setup_promtail = mocker.patch(
        "charms.loki_k8s.v0.loki_push_api.LogProxyConsumer._setup_promtail", return_value=None
    )
    return mocked_setup_promtail


@pytest.fixture()
def mocked_push_default_files(mocker: MockerFixture) -> MagicMock:
    mocked = mocker.patch("charm.KratosCharm._push_default_files")
    return mocked
