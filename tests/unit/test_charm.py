# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from charmed_kubeflow_chisme.exceptions import ErrorWithStatus
from charmed_kubeflow_chisme.lightkube.mocking import FakeApiError
from ops.model import ActiveStatus, BlockedStatus, MaintenanceStatus, WaitingStatus

CONTAINER_NAME = "kratos"


def test_on_install_sucess(harness, mocked_resource_handler, mocked_lightkube_client) -> None:
    harness.begin()

    harness.set_can_connect(CONTAINER_NAME, True)
    assert isinstance(harness.charm.unit.status, MaintenanceStatus)
    harness.charm.on.install.emit()

    mocked_resource_handler.apply.assert_called_once()

    assert isinstance(harness.charm.unit.status, ActiveStatus)


@pytest.mark.parametrize(
    "apply_error, raised_exception",
    (
        (FakeApiError(400), pytest.raises(FakeApiError)),
        (
            FakeApiError(403),
            pytest.raises(FakeApiError),
        ),
        (ErrorWithStatus("Something failed", BlockedStatus), pytest.raises(ErrorWithStatus)),
    ),
)
def test_on_install_error(harness, apply_error, raised_exception, mocked_lightkube_client) -> None:
    harness.begin()

    harness.charm.resource_handler.apply = MagicMock()
    harness.charm.resource_handler.apply.side_effect = apply_error

    harness.charm.on.install.emit()
    with raised_exception:
        harness.charm.resource_handler.apply()
    assert isinstance(harness.model.unit.status, BlockedStatus)


def test_pebble_ready_success(harness, mocked_resource_handler, mocked_lightkube_client) -> None:
    db_username = "fake_relation_id_1"
    db_password = "fake-password"

    harness.set_can_connect(CONTAINER_NAME, True)
    harness.set_leader(True)
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")
    harness.update_relation_data(
        db_relation_id,
        "postgresql-k8s",
        {
            "data": '{"database": "database", "extra-user-roles": "SUPERUSER"}',
            "endpoints": "postgresql-k8s-primary.namespace.svc.cluster.local:5432",
            "password": db_password,
            "username": db_username,
        },
    )

    initial_plan = harness.get_container_pebble_plan(CONTAINER_NAME)
    assert initial_plan.to_yaml() == "{}\n"

    harness.begin_with_initial_hooks()

    expected_plan = {
        "services": {
            CONTAINER_NAME: {
                "override": "replace",
                "summary": "Kratos Operator layer",
                "startup": "enabled",
                "command": "kratos serve all --config /etc/config/kratos.yaml",
            }
        }
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    assert expected_plan == updated_plan

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert harness.model.unit.status == ActiveStatus()


def test_pebble_ready_cannot_connect_container(
    harness, mocked_resource_handler, mocked_lightkube_client
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, False)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.charm.unit.status, WaitingStatus)


def test_pebble_ready_without_database_connection(
    harness, mocked_resource_handler, mocked_lightkube_client
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.charm.unit.status, BlockedStatus)


def test_on_database_created(harness, mocked_resource_handler, mocked_lightkube_client) -> None:
    db_username = "fake_relation_id_1"
    db_password = "fake-password"

    harness.begin()
    harness.charm._on_pebble_ready = MagicMock()
    harness.set_can_connect(CONTAINER_NAME, True)

    harness.set_leader(True)
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")
    harness.update_relation_data(
        db_relation_id,
        "postgresql-k8s",
        {
            "data": '{"database": "database", "extra-user-roles": "SUPERUSER"}',
            "endpoints": "postgresql-k8s-primary.namespace.svc.cluster.local:5432",
            "password": db_password,
            "username": db_username,
        },
    )

    assert harness.charm._stored.db_username == db_username
    assert harness.charm._stored.db_password == db_password
    harness.charm._on_pebble_ready.assert_called_once()


def test_on_remove_success(harness, mocked_resource_handler, mocked_lightkube_client) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.remove.emit()

    mocked_resource_handler.render_manifests.assert_called_once()


@pytest.mark.parametrize(
    "apply_error, raised_exception",
    (
        (FakeApiError(400), pytest.raises(FakeApiError)),
        (
            FakeApiError(403),
            pytest.raises(FakeApiError),
        ),
    ),
)
def test_on_remove_error(harness, apply_error, raised_exception, mocked_lightkube_client) -> None:
    harness.begin()

    harness.charm.resource_handler.apply = MagicMock()
    harness.charm.resource_handler.apply.side_effect = apply_error

    harness.charm.on.remove.emit()
    with raised_exception:
        harness.charm.resource_handler.apply()
