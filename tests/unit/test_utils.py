# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest

from integrations import LoginUIEndpointData
from utils import dict_to_action_output, login_ui_endpoints_is_ready, missing_login_ui_endpoints


def test_dict_to_action_output() -> None:
    input_ = {"a_b_c": 123}
    expected = {"a-b-c": 123}

    actual = dict_to_action_output(input_)

    assert actual == expected


def test_dict_to_action_output_with_nested_dict() -> None:
    input_ = {"a_b": {"c_d": "aba"}}
    expected = {"a-b": {"c-d": "aba"}}

    actual = dict_to_action_output(input_)

    assert actual == expected


def test_dict_to_action_output_without_underscore() -> None:
    input_ = {"a!@##$%^&*()-+=b": {"c123d": "aba"}}

    actual = dict_to_action_output(input_)

    assert actual == input_


def test_dict_to_action_output_with_empty_dict() -> None:
    actual = dict_to_action_output({})

    assert actual == {}


class TestMissingLoginUIEndpoints:
    """The verification flow block is rendered unguarded, so its URL is required.

    Rendering it without one yields `ui_url:` with no value, which Kratos rejects as null
    and which crash-loops the workload — so the charm must block instead of writing it.
    """

    def charm(self, *, verification: bool, local_idp: bool = True) -> MagicMock:
        charm = MagicMock()
        charm.charm_config = {
            "enable_verification": verification,
            "enable_local_idp": local_idp,
        }
        return charm

    @pytest.mark.parametrize(
        "verification, local_idp",
        [(False, True), (False, False), (True, False)],
        ids=["verification-off", "both-off", "local-idp-off"],
    )
    def test_not_required_when_verification_flow_is_not_rendered(
        self, verification: bool, local_idp: bool
    ) -> None:
        charm = self.charm(verification=verification, local_idp=local_idp)

        with patch.object(LoginUIEndpointData, "load", return_value=LoginUIEndpointData()):
            assert missing_login_ui_endpoints(charm) == ()
            assert login_ui_endpoints_is_ready(charm)

    def test_missing_when_verification_is_enabled_without_an_endpoint(self) -> None:
        charm = self.charm(verification=True)

        with patch.object(LoginUIEndpointData, "load", return_value=LoginUIEndpointData()):
            assert missing_login_ui_endpoints(charm) == ("verification",)
            assert not login_ui_endpoints_is_ready(charm)

    def test_ready_when_verification_endpoint_is_present(self) -> None:
        charm = self.charm(verification=True)
        endpoints = LoginUIEndpointData(verification_url="http://login-ui/ui/verification")

        with patch.object(LoginUIEndpointData, "load", return_value=endpoints):
            assert missing_login_ui_endpoints(charm) == ()
            assert login_ui_endpoints_is_ready(charm)

    def test_other_absent_endpoints_do_not_block(self) -> None:
        """Every other flow block self-guards, so absent optional endpoints must not block."""
        charm = self.charm(verification=True)
        endpoints = LoginUIEndpointData(verification_url="http://login-ui/ui/verification")

        with patch.object(LoginUIEndpointData, "load", return_value=endpoints):
            assert endpoints.is_ready() is False
            assert login_ui_endpoints_is_ready(charm)
