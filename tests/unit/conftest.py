# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from ops.testing import Harness

from charm import KratosCharm


@pytest.fixture()
def harness() -> None:
    harness = Harness(KratosCharm)
    harness.set_leader(True)
    return harness


@pytest.fixture()
def mocked_lightkube_client(mocker):
    mocked_client = MagicMock()
    mocked_client_factory = mocker.patch("charm.Client")
    mocked_client_factory.return_value = mocked_client
    yield mocked_client


@pytest.fixture()
def mocked_resource_handler(mocker):
    """Yields a mocked lightkube Client."""
    mocked_resource_handler = MagicMock()
    mocked_resource_handler_factory = mocker.patch("charm.KubernetesResourceHandler")
    mocked_resource_handler_factory.return_value = mocked_resource_handler
    yield mocked_resource_handler
