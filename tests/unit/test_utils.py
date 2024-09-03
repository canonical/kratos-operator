# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from io import StringIO
from unittest.mock import MagicMock, _Sentinel, sentinel

from ops import ActiveStatus, CharmBase, HookEvent
from pytest_mock import MockerFixture

from tests.unit.conftest import harness
from utils import dict_to_action_output, normalise_url, run_after_config_updated


def test_dict_to_action_output() -> None:
    dic = {"a_b_c": 123}
    expected_dict = {"a-b-c": 123}

    out = dict_to_action_output(dic)

    assert expected_dict == out


def test_dict_to_action_output_with_nested_dict() -> None:
    dic = {"a_b": {"c_d": "aba"}}
    expected_dict = {"a-b": {"c-d": "aba"}}

    out = dict_to_action_output(dic)

    assert expected_dict == out


def test_dict_to_action_output_without_underscore() -> None:
    dic = {"a!@##$%^&*()-+=b": {"c123d": "aba"}}

    out = dict_to_action_output(dic)

    assert dic == out


def test_dict_to_action_output_with_empty_dict() -> None:
    dic = {}

    out = dict_to_action_output(dic)

    assert dic == out


def test_normalise_url_with_subpatch() -> None:
    url = "http://ingress:80/path/subpath"
    expected_url = "https://ingress/path/subpath"

    res_url = normalise_url(url)

    assert res_url == expected_url


def test_normalise_url_without_subpatch() -> None:
    url = "http://ingress:80/"
    expected_url = "https://ingress/"

    res_url = normalise_url(url)

    assert res_url == expected_url


def test_normalise_url_without_trailing_slash() -> None:
    url = "http://ingress:80"
    expected_url = "https://ingress"

    res_url = normalise_url(url)

    assert res_url == expected_url


class TestUtils:
    def test_run_after_config_updated(
        self,
        harness: harness,
        mocked_hook_event: MagicMock,
        mocker: MockerFixture,
    ) -> None:
        mocker.patch("ops.model.Container.pull", return_value=StringIO("abc"))
        mocker.patch("charm.KratosCharm._render_conf_file", return_value="abc")

        @run_after_config_updated
        def wrapped(charm: CharmBase, event: HookEvent) -> _Sentinel:
            charm.unit.status = ActiveStatus()
            return sentinel

        assert wrapped(harness.charm, mocked_hook_event) is sentinel
        assert isinstance(harness.model.unit.status, ActiveStatus)
