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
    mocked_lightkube_client.patch.assert_called_once()

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
def test_on_install_error(
    harness,
    apply_error,
    raised_exception,
) -> None:
    harness.begin()

    harness.charm.resource_handler.apply = MagicMock()
    harness.charm.resource_handler.apply.side_effect = apply_error

    harness.charm.on.install.emit()
    with raised_exception:
        harness.charm.resource_handler.apply()
    assert isinstance(harness.model.unit.status, BlockedStatus)


def test_pebble_ready_success(harness) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)
    initial_plan = harness.get_container_pebble_plan(CONTAINER_NAME)
    assert initial_plan.to_yaml() == "{}\n"

    expected_plan = {
        "services": {
            CONTAINER_NAME: {
                "override": "replace",
                "summary": "Kratos Operator layer",
                "startup": "enabled",
                "command": "kratos serve all --config /etc/config/kratos.yaml",
                "environment": {
                    "DSN": "postgres://username:password@10.152.183.152:5432/postgres",
                    "COURIER_SMTP_CONNECTION_URI": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true",
                },
            }
        }
    }
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    assert expected_plan == updated_plan

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert harness.model.unit.status == ActiveStatus()


def test_pebble_ready_cannot_connect_container(harness) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, False)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.charm.unit.status, WaitingStatus)


def test_on_remove_success(harness, mocked_resource_handler) -> None:
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
def test_on_remove_error(
    harness,
    apply_error,
    raised_exception,
) -> None:
    harness.begin()

    harness.charm.resource_handler.apply = MagicMock()
    harness.charm.resource_handler.apply.side_effect = apply_error

    harness.charm.on.remove.emit()
    with raised_exception:
        harness.charm.resource_handler.apply()
