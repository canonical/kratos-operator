# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock, patch

import pytest
from ops.pebble import ExecError

from cli import CommandLine


class TestCommandLine:
    @pytest.fixture
    def command_line(self, mocked_container: MagicMock) -> CommandLine:
        return CommandLine(mocked_container)

    def test_get_admin_service_version(self, command_line: CommandLine) -> None:
        expected = "v1.3.1"
        with patch.object(
            command_line,
            "_run_cmd",
            return_value=(
                f"Version:    {expected}\n"
                f"Build Commit:    e23751bbc5704efd58acc1132b987ff7fb0412ac\n"
                f"Build Timestamp:    2024-05-01T07:49:53Z"
            ),
        ) as run_cmd:
            actual = command_line.get_service_version()
            assert actual == expected
            run_cmd.assert_called_with(["kratos", "version"])

    def test_migrate(self, command_line: CommandLine) -> None:
        dsn = "postgres://user:password@localhost/db"
        with patch.object(command_line, "_run_cmd") as run_cmd:
            command_line.migrate(dsn)

        expected_cmd = [
            "kratos",
            "migrate",
            "sql",
            "-e",
            "--yes",
        ]
        expected_environment = {"DSN": dsn}
        run_cmd.assert_called_once_with(
            expected_cmd, timeout=120, environment=expected_environment
        )

    def test_run_cmd(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd, expected = ["cmd"], "stdout"

        mocked_process = MagicMock(wait_output=MagicMock(return_value=(expected, "")))
        mocked_container.exec.return_value = mocked_process

        actual = command_line._run_cmd(cmd)

        assert actual == expected
        mocked_container.exec.assert_called_once_with(cmd, timeout=20, environment=None)

    def test_run_cmd_failed(self, mocked_container: MagicMock, command_line: CommandLine) -> None:
        cmd = ["cmd"]

        mocked_process = MagicMock(wait_output=MagicMock(side_effect=ExecError(cmd, 1, "", "")))
        mocked_container.exec.return_value = mocked_process

        with pytest.raises(ExecError):
            command_line._run_cmd(cmd)
