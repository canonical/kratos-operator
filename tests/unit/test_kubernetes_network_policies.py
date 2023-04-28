# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from charms.kratos.v0.kubernetes_network_policies import (
    KubernetesNetworkPoliciesHandler,
    NetworkPoliciesHandlerError,
)
from httpx import Response
from lightkube import ApiError, Client


@pytest.fixture(autouse=True)
def mock_lk_client(mocker: MockerFixture) -> None:
    mocker.patch("charms.kratos.v0.kubernetes_network_policies.Client")


@pytest.fixture()
def mock_charm() -> MagicMock:
    charm = MagicMock()
    charm.app = MagicMock()
    charm.app.name = "app"
    charm.model = MagicMock()
    charm.model.name = "model"
    return charm


@pytest.fixture()
def policy_handler(mock_charm: MagicMock) -> KubernetesNetworkPoliciesHandler:
    handler = KubernetesNetworkPoliciesHandler(mock_charm)
    handler.client = MagicMock(spec=Client)
    return handler


def test_apply_ingress_policies_allow(policy_handler: KubernetesNetworkPoliciesHandler) -> None:
    policy_handler.apply_ingress_policies([(8080, [])])

    policy_handler.client.apply.assert_called()


def test_apply_ingress_policies_allow_no_trust(
    policy_handler: KubernetesNetworkPoliciesHandler, caplog: pytest.LogCaptureFixture
) -> None:
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    policy_handler.client.apply = MagicMock(side_effect=ApiError(response=resp))

    with pytest.raises(NetworkPoliciesHandlerError):
        policy_handler.apply_ingress_policies([(8080, [])])

    assert caplog.messages[0].startswith(
        "Kubernetes resources patch failed: `juju trust` this application."
    )


def test_delete_ingress_policies(policy_handler: KubernetesNetworkPoliciesHandler) -> None:
    policy_handler.delete_ingress_policies()

    policy_handler.client.delete.assert_called()


def test_delete_ingress_policies_allow_no_trust(
    policy_handler: KubernetesNetworkPoliciesHandler, caplog: pytest.LogCaptureFixture
) -> None:
    resp = Response(status_code=403, json={"message": "Forbidden", "code": 403})
    policy_handler.client.delete = MagicMock(side_effect=ApiError(response=resp))

    with pytest.raises(NetworkPoliciesHandlerError):
        policy_handler.delete_ingress_policies([(8080, [])])

    assert caplog.messages[0].startswith(
        "Kubernetes resources patch failed: `juju trust` this application."
    )
