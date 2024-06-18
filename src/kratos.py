# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""A helper class for interacting with the kratos API."""

import json
import logging
import re
from os.path import join
from typing import Dict, List, Optional

import requests
from ops.model import Container

logger = logging.getLogger(__name__)


class KratosAPI:
    """A helper object for interacting with the kratos API."""

    def __init__(self, kratos_admin_url: str, container: Container, config_file_path: str) -> None:
        self.kratos_admin_url = kratos_admin_url
        self.container = container
        self.config_file_path = config_file_path

    def create_identity(
        self, traits: Dict, schema_id: str, password: Optional[str] = None
    ) -> Dict:
        """Create an identity."""
        cmd = [
            "kratos",
            "import",
            "identities",
            "--endpoint",
            self.kratos_admin_url,
            "--format",
            "json",
        ]

        identity = {"traits": traits, "schema_id": schema_id}
        if password:
            identity["credentials"] = {"password": {"config": {"password": password}}}

        cmd_output = json.loads(self._run_cmd(cmd, input_=json.dumps(identity)))
        logger.info(f"Successfully created identity: {cmd_output.get('id')}")
        return cmd_output

    def get_identity(self, identity_id: str) -> Dict:
        """Get an identity."""
        cmd = [
            "kratos",
            "get",
            "identity",
            "--endpoint",
            self.kratos_admin_url,
            "--format",
            "json",
            identity_id,
        ]

        cmd_output = json.loads(self._run_cmd(cmd))
        logger.info(f"Successfully fetched identity: {identity_id}")
        return cmd_output

    def delete_identity(self, identity_id: str) -> str:
        """Get an identity."""
        cmd = [
            "kratos",
            "delete",
            "identity",
            "--endpoint",
            self.kratos_admin_url,
            "--format",
            "json",
            identity_id,
        ]

        cmd_output = self._run_cmd(cmd)
        logger.info(f"Successfully deleted identity: {identity_id}")
        return cmd_output

    def list_identities(self) -> List:
        """List all identities."""
        cmd = [
            "kratos",
            "list",
            "identities",
            "--endpoint",
            self.kratos_admin_url,
            "--format",
            "json",
        ]

        # TODO: Consider reading from the stream instead of waiting for output
        cmd_output = json.loads(self._run_cmd(cmd))
        identities = cmd_output.get("identities")
        logger.info("Successfully fetched all identities")

        return identities

    def get_identity_from_email(self, email: str) -> Optional[Dict]:
        """Get an identity using an email.

        This will fetch all identities and iterate over them in memory.
        """
        ids = self.list_identities()
        id_ = [identity for identity in ids if identity["traits"].get("email") == email]
        return id_[0] if id_ else None

    def recover_password_with_code(self, identity_id: str, expires_in: str = "1h") -> Dict:
        """Create a one time code for recovering an identity's password."""
        url = join(self.kratos_admin_url, "admin/recovery/code")
        data = {"identity_id": identity_id, "expires_in": expires_in}

        r = requests.post(url, json=data)
        r.raise_for_status()

        return r.json()

    def recover_password_with_link(self, identity_id: str, expires_in: str = "1h") -> Dict:
        """Create a magic link for recovering an identity's password."""
        url = join(self.kratos_admin_url, "admin/recovery/link")
        data = {"identity_id": identity_id, "expires_in": expires_in}

        r = requests.post(url, json=data)
        r.raise_for_status()

        return r.json()

    def run_migration(self, dsn=None, timeout: float = 120) -> str:
        """Run an sql migration."""
        cmd = [
            "kratos",
            "migrate",
            "sql",
            "-e",
            "--yes",
        ]
        if dsn:
            env = {"DSN": dsn}
        else:
            cmd.append("--config")
            cmd.append(self.config_file_path)
            env = None

        return self._run_cmd(cmd, timeout=timeout, environment=env)

    def get_version(self) -> str:
        """Get the version of the kratos binary."""
        cmd = ["kratos", "version"]

        stdout = self._run_cmd(cmd)

        # Output has the format:
        # Version:    {version}
        # Build Commit:   {hash}
        # Build Timestamp: {time}
        out_re = r"Version:\s*(.+)\nBuild Commit:\s*(.+)\nBuild Timestamp:\s*(.+)"
        versions = re.findall(out_re, stdout)[0]

        return versions[0]

    def _run_cmd(
        self,
        cmd: List[str],
        timeout: float = 20,
        input_: Optional[str] = None,
        environment: Optional[Dict] = None,
    ) -> str:
        logger.debug(f"Running cmd: {cmd}")
        process = self.container.exec(cmd, environment=environment, timeout=timeout)
        if input_:
            process.stdin.write(input_)
            process.stdin.close()
        output, _ = process.wait_output()

        return output.decode() if isinstance(output, bytes) else output
