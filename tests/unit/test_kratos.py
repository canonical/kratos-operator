# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Dict, Tuple
from unittest.mock import MagicMock

import pytest
from ops.pebble import ExecError
from pytest_mock import MockerFixture

from kratos import KratosAPI


@pytest.mark.parametrize(
    "function_name,call_args",
    [
        ("create_identity", ({}, {})),
        ("get_identity", ("id",)),
        ("delete_identity", ("id",)),
        ("list_identities", ()),
        ("get_identity_from_email", ("mail",)),
        ("run_migration", ()),
    ],
)
def test_pebble_exec_error(
    kratos_api: KratosAPI,
    function_name: str,
    call_args: Tuple,
) -> None:
    kratos_api.container.exec.side_effect = ExecError(
        command=["some", "command"], exit_code=1, stdout="", stderr="Error"
    )

    with pytest.raises(ExecError):
        getattr(kratos_api, function_name)(*call_args)


def test_create_identity(
    kratos_api: KratosAPI, kratos_identity_json: Dict, mocked_kratos_process: MagicMock
) -> None:
    mocked_kratos_process.wait_output.return_value = (json.dumps(kratos_identity_json), None)
    traits = {
        "email": kratos_identity_json["traits"]["email"],
    }
    schema_id = "user"
    expected_stdin = json.dumps(dict(traits=traits, schema_id=schema_id))

    kratos_api.create_identity(traits, schema_id)

    assert kratos_api.container.exec.call_args[0][0] == [
        "kratos",
        "import",
        "identities",
        "--endpoint",
        kratos_api.kratos_admin_url,
        "--format",
        "json",
    ]
    mocked_kratos_process.stdin.write.assert_called_with(expected_stdin)


def test_create_identity_with_password(
    kratos_api: KratosAPI, kratos_identity_json: Dict, mocked_kratos_process: MagicMock
) -> None:
    mocked_kratos_process.wait_output.return_value = (json.dumps(kratos_identity_json), None)
    traits = {
        "email": kratos_identity_json["traits"]["email"],
    }
    schema_id = "user"
    password = "pass"
    expected_stdin = json.dumps(
        dict(
            traits=traits,
            schema_id=schema_id,
            credentials={"password": {"config": {"password": password}}},
        )
    )

    kratos_api.create_identity(traits, schema_id, password=password)

    assert kratos_api.container.exec.call_args[0][0] == [
        "kratos",
        "import",
        "identities",
        "--endpoint",
        kratos_api.kratos_admin_url,
        "--format",
        "json",
    ]
    mocked_kratos_process.stdin.write.assert_called_with(expected_stdin)


def test_get_identity(
    kratos_api: KratosAPI, kratos_identity_json: Dict, mocked_kratos_process: MagicMock
) -> None:
    mocked_kratos_process.wait_output.return_value = (json.dumps(kratos_identity_json), None)

    kratos_api.get_identity(identity_id := kratos_identity_json["id"])

    assert kratos_api.container.exec.call_args[0][0] == [
        "kratos",
        "get",
        "identity",
        "--endpoint",
        kratos_api.kratos_admin_url,
        "--format",
        "json",
        identity_id,
    ]


def test_delete_identity(
    kratos_api: KratosAPI, kratos_identity_json: Dict, mocked_kratos_process: MagicMock
) -> None:
    mocked_kratos_process.wait_output.return_value = (json.dumps(kratos_identity_json), None)

    kratos_api.delete_identity(identity_id := kratos_identity_json["id"])

    assert kratos_api.container.exec.call_args[0][0] == [
        "kratos",
        "delete",
        "identity",
        "--endpoint",
        kratos_api.kratos_admin_url,
        "--format",
        "json",
        identity_id,
    ]


def test_list_identities(
    kratos_api: KratosAPI, kratos_identity_json: Dict, mocked_kratos_process: MagicMock
) -> None:
    mocked_kratos_process.wait_output.return_value = (json.dumps([kratos_identity_json]), None)

    kratos_api.list_identities()

    assert kratos_api.container.exec.call_args[0][0] == [
        "kratos",
        "list",
        "identities",
        "--endpoint",
        kratos_api.kratos_admin_url,
        "--format",
        "json",
    ]


def test_get_identity_from_email(
    kratos_api: KratosAPI, kratos_identity_json: Dict, mocked_kratos_process: MagicMock
) -> None:
    mocked_kratos_process.wait_output.return_value = (json.dumps([kratos_identity_json]), None)

    identity = kratos_api.get_identity_from_email(kratos_identity_json["traits"]["email"])

    assert kratos_api.container.exec.call_args[0][0] == [
        "kratos",
        "list",
        "identities",
        "--endpoint",
        kratos_api.kratos_admin_url,
        "--format",
        "json",
    ]
    assert identity == kratos_identity_json


def test_get_identity_from_email_with_wrong_mail(
    kratos_api: KratosAPI, kratos_identity_json: Dict, mocked_kratos_process: MagicMock
) -> None:
    mocked_kratos_process.wait_output.return_value = (json.dumps([kratos_identity_json]), None)

    identity = kratos_api.get_identity_from_email("mail")

    assert identity is None


def test_recover_password_with_code(
    kratos_api: KratosAPI, mocker: MockerFixture, recover_password_with_code_resp: Dict
) -> None:
    mocked_resp = MagicMock()
    mocked_resp.json.return_value = recover_password_with_code_resp
    mocker.patch("requests.post", return_value=mocked_resp)

    ret = kratos_api.recover_password_with_code("identity_id")

    assert ret == recover_password_with_code_resp


def test_recover_password_with_link(
    kratos_api: KratosAPI, mocker: MockerFixture, recover_password_with_link_resp: Dict
) -> None:
    mocked_resp = MagicMock()
    mocked_resp.json.return_value = recover_password_with_link_resp
    mocker.patch("requests.post", return_value=mocked_resp)

    ret = kratos_api.recover_password_with_link("identity_id")

    assert ret == recover_password_with_link_resp


def test_run_migration(kratos_api: KratosAPI, mocked_kratos_process: MagicMock) -> None:
    expected_output = "success"
    mocked_kratos_process.wait_output.return_value = (expected_output, None)

    cmd_output = kratos_api.run_migration()

    assert kratos_api.container.exec.call_args[0][0] == [
        "kratos",
        "migrate",
        "sql",
        "-e",
        "--yes",
        "--config",
        kratos_api.config_file_path,
    ]

    assert expected_output == cmd_output
