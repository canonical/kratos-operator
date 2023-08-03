# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from httpx import Response
from lightkube import ApiError

from charm import KratosCharm
from config_map import ConfigMapHandler


@pytest.fixture
def handler(lk_client: MagicMock) -> ConfigMapHandler:
    charm = MagicMock(spec=KratosCharm)
    handler = ConfigMapHandler(lk_client, charm)
    return handler


def test_create_map_already_exists(lk_client: MagicMock, handler: ConfigMapHandler) -> None:
    handler._create_map("config")

    assert lk_client.get.called
    assert not lk_client.create.called


def test_create_map(lk_client: MagicMock, handler: ConfigMapHandler) -> None:
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    lk_client.get.side_effect = ApiError(response=resp)

    handler._create_map("config")

    assert lk_client.get.called
    assert lk_client.create.called


def test_update_map(lk_client: MagicMock, handler: ConfigMapHandler) -> None:
    data = {"data": 1}

    handler._update_map("config", data)

    assert lk_client.get.called
    assert lk_client.replace.called
    assert lk_client.replace.call_args[0][0].data == data


def test_update_map_error(lk_client: MagicMock, handler: ConfigMapHandler) -> None:
    data = {"data": 1}
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    lk_client.get.side_effect = ApiError(response=resp)

    handler._update_map("config", data)

    assert lk_client.get.called
    assert not lk_client.replace.called


def test_get_map(lk_client: MagicMock, handler: ConfigMapHandler) -> None:
    data = {"data": 1}
    lk_client.get.return_value.data = data

    d = handler._get_map("config")

    assert lk_client.get.called
    assert d == data


def test_get_map_error(lk_client: MagicMock, handler: ConfigMapHandler) -> None:
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    lk_client.get.side_effect = ApiError(response=resp)

    d = handler._get_map("config")

    assert lk_client.get.called
    assert d == {}


def test_delete_map(lk_client: MagicMock, handler: ConfigMapHandler) -> None:
    data = {"data": 1}
    lk_client.delete.return_value.data = data

    handler._delete_map("config")

    assert lk_client.delete.called


def test_delete_map_error(lk_client: MagicMock, handler: ConfigMapHandler) -> None:
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    lk_client.delete.side_effect = ApiError(response=resp)

    with pytest.raises(ValueError):
        handler._delete_map("config")
