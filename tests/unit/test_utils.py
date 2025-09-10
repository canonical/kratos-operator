# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from utils import dict_to_action_output


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
