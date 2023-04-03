# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Dict, Generator
from unittest.mock import MagicMock

import pytest
from ops.pebble import ExecError
from ops.testing import Harness
from pytest_mock import MockerFixture

from charm import KratosCharm


@pytest.fixture()
def harness(mocked_kubernetes_service_patcher) -> Harness:
    harness = Harness(KratosCharm)
    harness.set_model_name("kratos-model")
    harness.set_can_connect("kratos", True)
    harness.set_leader(True)
    harness.begin()
    return harness


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker):
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    yield mocked_service_patcher


@pytest.fixture()
def mocked_kratos_is_running(mocker: MockerFixture) -> Generator:
    return mocker.patch("charm.KratosCharm._kratos_service_is_running", return_value=True)


@pytest.fixture()
def mocked_fqdn(mocker):
    mocked_fqdn = mocker.patch("socket.getfqdn")
    mocked_fqdn.return_value = "kratos"
    return mocked_fqdn


@pytest.fixture()
def mocked_container(harness, mocker):
    container = harness.model.unit.get_container("kratos")
    container.restart = mocker.MagicMock()
    return container


@pytest.fixture()
def mocked_pebble_exec(mocker):
    mocked_pebble_exec = mocker.patch("ops.model.Container.exec")
    yield mocked_pebble_exec


@pytest.fixture()
def mocked_pebble_exec_success(mocker, mocked_pebble_exec):
    mocked_process = mocker.patch("ops.pebble.ExecProcess")
    mocked_process.wait_output.return_value = ("Success", None)
    mocked_pebble_exec.return_value = mocked_process
    yield mocked_pebble_exec


@pytest.fixture()
def mocked_pebble_exec_failed(mocked_pebble_exec):
    mocked_pebble_exec.side_effect = ExecError(
        exit_code=400, stderr="Failed to execute", stdout="Failed", command="test command"
    )
    yield


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
def mocked_recover_password_with_code(mocker: MockerFixture) -> MagicMock:
    ret = {
        "recovery_link": "http://kratos-ui/recovery?flow=2ebd739f-7c9c-404e-8ec9-769c055f5393",
        "recovery_code": "123456",
        "expires_at": "2023-04-03T21:47:52.869721347Z",
    }
    mock = mocker.patch("charm.KratosAPI.recover_password_with_code", return_value=ret)
    return mock


@pytest.fixture()
def mocked_recover_password_with_link(mocker: MockerFixture) -> MagicMock:
    ret = {
        "recovery_link": "http://kratos-ui/self-service/recovery?flow=e18560f9-8f50-4679-bcc9-d6cea2bb203f&token=5UJ9GgQTxvSp53zkwgOkjG9eRvnYjEYq",
        "expires_at": "2023-04-03T21:47:52.869721347Z",
    }
    mock = mocker.patch("charm.KratosAPI.recover_password_with_link", return_value=ret)
    return mock


@pytest.fixture()
def mocked_create_identity(mocker: MockerFixture, kratos_identity_json: Dict) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.create_identity", return_value=kratos_identity_json)
    return mock


@pytest.fixture()
def mocked_run_migration(mocker: MockerFixture) -> MagicMock:
    mock = mocker.patch("charm.KratosAPI.run_migration", return_value=(None, None))
    return mock
