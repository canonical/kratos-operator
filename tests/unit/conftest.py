# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from ops.testing import Harness

from charm import KratosCharm


@pytest.fixture()
def harness(mocked_resource_handler, mocked_lightkube_client) -> None:
    harness = Harness(KratosCharm)
    harness.set_leader(True)
    harness.begin()
    return harness


@pytest.fixture()
def mocked_lightkube_client(mocker):
    mocked_client = mocker.patch("charm.Client")
    mocked_client.return_value = MagicMock()
    yield mocked_client


@pytest.fixture()
def mocked_resource_handler(mocker):
    mocked_resource_handler = mocker.patch("charm.KubernetesResourceHandler")
    mocked_resource_handler.return_value = MagicMock()
    yield mocked_resource_handler
