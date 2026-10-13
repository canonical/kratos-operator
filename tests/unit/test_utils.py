# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest

from utils import dict_to_action_output, multitenancy_config_is_valid


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


@pytest.mark.parametrize(
    "multitenancy, enable_verification, sequencing, expected",
    [
        (False, False, True, True),
        (True, True, False, True),
        (True, False, False, False),
        (True, True, True, False),
    ],
)
def test_multitenancy_config_is_valid(
    multitenancy: bool, enable_verification: bool, sequencing: bool, expected: bool
) -> None:
    charm = MagicMock()
    charm.charm_config = {
        "enable_verification": enable_verification,
        "enable_oidc_webauthn_sequencing": sequencing,
    }

    with patch("utils.LoginUIEndpointData.load") as mocked_load:
        mocked_load.return_value.multitenancy = multitenancy

        assert multitenancy_config_is_valid(charm) is expected
