# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from ops import ModelError
from pytest_mock import MockerFixture
from scenario import CheckInfo

from configs import ConfigFile
from constants import (
    CA_BUNDLE_PATH,
    CONFIG_FILE_PATH,
    KRATOS_ADMIN_PORT,
    KRATOS_PUBLIC_PORT,
    WORKLOAD_SERVICE,
)
from env_vars import DEFAULT_CONTAINER_ENV, EnvVarConvertible
from exceptions import PebbleServiceError
from services import PebbleService, WorkloadService


class TestWorkloadService:
    @pytest.fixture
    def workload_service(
        self, mocked_container: MagicMock, mocked_unit: MagicMock
    ) -> WorkloadService:
        return WorkloadService(mocked_unit)

    @pytest.mark.parametrize("version, expected", [("v1.0.0", "v1.0.0"), (None, "")])
    def test_get_version(
        self, workload_service: WorkloadService, version: Optional[str], expected: str
    ) -> None:
        with patch("cli.CommandLine.get_service_version", return_value=version):
            assert workload_service.version == expected

    def test_set_version(self, mocked_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.version = "v1.0.0"
        mocked_unit.set_workload_version.assert_called_once_with("v1.0.0")

    def test_set_empty_version(
        self, mocked_unit: MagicMock, workload_service: WorkloadService
    ) -> None:
        workload_service.version = ""
        mocked_unit.set_workload_version.assert_not_called()

    def test_set_version_with_error(
        self,
        mocked_unit: MagicMock,
        workload_service: WorkloadService,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        error_msg = "Error from unit"
        mocked_unit.set_workload_version.side_effect = Exception(error_msg)

        with caplog.at_level("ERROR"):
            workload_service.version = "v1.0.0"

        mocked_unit.set_workload_version.assert_called_once_with("v1.0.0")
        assert f"Failed to set workload version: {error_msg}" in caplog.text

    def test_is_running(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        mocked_service_info = MagicMock(is_running=MagicMock(return_value=True))
        check = CheckInfo(name="ready")
        mocked_container.get_checks.return_value = {"ready": check}

        with patch.object(
            mocked_container, "get_service", return_value=mocked_service_info
        ) as get_service:
            is_running = workload_service.is_running()

        assert is_running is True
        get_service.assert_called_once_with(WORKLOAD_SERVICE)

    def test_is_running_with_error(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        with patch.object(mocked_container, "get_service", side_effect=ModelError):
            is_running = workload_service.is_running()

        assert is_running is False

    def test_open_ports(self, mocked_unit: MagicMock, workload_service: WorkloadService) -> None:
        workload_service.open_ports()

        assert mocked_unit.open_port.call_count == 2
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=KRATOS_PUBLIC_PORT)
        mocked_unit.open_port.assert_any_call(protocol="tcp", port=KRATOS_ADMIN_PORT)

    def test_push_ca_certs(
        self, mocked_container: MagicMock, workload_service: WorkloadService
    ) -> None:
        workload_service.push_ca_certs("ca_certs")

        mocked_container.push.assert_called_with(str(CA_BUNDLE_PATH), "ca_certs", make_dirs=True)


class TestPebbleService:
    @pytest.fixture
    def pebble_service(self, mocked_unit: MagicMock) -> PebbleService:
        return PebbleService(mocked_unit)

    @pytest.fixture
    def mocked_config_file(self, mocker: MockerFixture) -> MagicMock:
        mocked = mocker.patch("charm.ConfigFile.from_workload_container")
        mocked.return_value = ConfigFile("config_file")
        return mocked

    @patch("ops.pebble.Layer")
    def test_plan_when_config_files_mismatch(
        self,
        mocked_layer: MagicMock,
        mocked_config_file: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        pebble_service.plan(mocked_layer, config_file=ConfigFile("new_config_file"))

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_SERVICE, mocked_layer, combine=True
        )
        mocked_container.push.assert_called_once_with(
            CONFIG_FILE_PATH, "new_config_file", make_dirs=True
        )
        mocked_container.restart.assert_called_once()
        mocked_container.replan.assert_not_called()

    @patch("ops.pebble.Layer")
    def test_plan_when_config_files_match(
        self,
        mocked_layer: MagicMock,
        mocked_config_file: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        pebble_service.plan(mocked_layer, config_file=ConfigFile("config_file"))

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_SERVICE, mocked_layer, combine=True
        )
        mocked_container.push.assert_not_called()
        mocked_container.restart.assert_not_called()
        mocked_container.replan.assert_called_once()

    @patch("ops.pebble.Layer")
    def test_plan_failure(
        self,
        mocked_layer: MagicMock,
        mocked_config_file: MagicMock,
        mocked_container: MagicMock,
        pebble_service: PebbleService,
    ) -> None:
        with (
            patch.object(mocked_container, "replan", side_effect=Exception) as replan,
            pytest.raises(PebbleServiceError),
        ):
            pebble_service.plan(mocked_layer, config_file=ConfigFile("config_file"))

        mocked_container.add_layer.assert_called_once_with(
            WORKLOAD_SERVICE, mocked_layer, combine=True
        )
        replan.assert_called_once()

    def test_render_pebble_layer(self, pebble_service: PebbleService) -> None:
        data_source = MagicMock(spec=EnvVarConvertible)
        data_source.to_env_vars.return_value = {"key1": "value1"}

        another_data_source = MagicMock(spec=EnvVarConvertible)
        another_data_source.to_env_vars.return_value = {"key2": "value2"}

        expected_env_vars = {
            **DEFAULT_CONTAINER_ENV,
            "key1": "value1",
            "key2": "value2",
        }

        layer = pebble_service.render_pebble_layer(data_source, another_data_source)

        layer_dict = layer.to_dict()
        assert layer_dict["services"][WORKLOAD_SERVICE]["environment"] == expected_env_vars
