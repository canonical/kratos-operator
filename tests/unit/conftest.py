# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import pytest
from ops.testing import Harness

from charm import KratosCharm


@pytest.fixture()
def harness() -> None:
    harness = Harness(KratosCharm)
    harness.set_model_name("kratos-model")
    harness.set_leader(True)
    return harness


@pytest.fixture()
def mocked_kubernetes_service_patcher(mocker):
    mocked_service_patcher = mocker.patch("charm.KubernetesServicePatch")
    mocked_service_patcher.return_value = lambda x, y: None
    yield mocked_service_patcher


@pytest.fixture()
def mocked_sql_migration(mocker):
    mocked_sql_migration = mocker.patch("charm.KratosCharm._run_sql_migration")
    yield mocked_sql_migration


@pytest.fixture()
def mocked_update_container(mocker):
    mocked_update_container = mocker.patch("charm.KratosCharm._update_container")
    yield mocked_update_container
