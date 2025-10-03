# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import re
from typing import Optional

from ops import Container
from ops.pebble import Error, ExecError

from exceptions import MigrationError

logger = logging.getLogger(__name__)

VERSION_REGEX = re.compile(r"Version:\s+(?P<version>v\d+\.\d+\.\d+)")


class CommandLine:
    def __init__(self, container: Container):
        self.container = container

    def get_service_version(self) -> Optional[str]:
        """Get Kratos application version.

        Version command output format:
        # Version:    {version}
        # Build Commit:   {hash}
        # Build Timestamp: {time}
        """
        cmd = ["kratos", "version"]

        try:
            stdout = self._run_cmd(cmd)
        except Error as err:
            logger.error("Failed to fetch the Kratos version: %s", err)
            return None

        matched = VERSION_REGEX.search(stdout)
        return matched.group("version") if matched else None

    def migrate(self, dsn: str, timeout: float = 120) -> None:
        """Apply Kratos database migration.

        More information: https://www.ory.sh/docs/kratos/cli/kratos-migrate-sql
        """
        cmd = [
            "kratos",
            "migrate",
            "sql",
            "-e",
            "--yes",
        ]

        try:
            self._run_cmd(cmd, timeout=timeout, environment={"DSN": dsn})
        except Error as err:
            logger.error("Failed to migrate Kratos: %s", err)
            raise MigrationError from err

    def _run_cmd(
        self,
        cmd: list[str],
        timeout: float = 20,
        environment: Optional[dict] = None,
    ) -> str:
        logger.debug(f"Running command: {cmd}")
        process = self.container.exec(cmd, environment=environment, timeout=timeout)

        try:
            stdout, _ = process.wait_output()
        except ExecError as err:
            logger.error("Exited with code: %d. Error: %s", err.exit_code, err.stderr)
            raise

        return stdout.decode() if isinstance(stdout, bytes) else stdout
