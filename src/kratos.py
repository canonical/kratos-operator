# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""A helper class for interacting with the kratos API."""

import json
import logging
from os.path import join
from typing import Dict, List, Optional, Tuple

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

        stdout, _ = self._run_cmd(cmd, stdin=json.dumps(identity))
        json_stdout = json.loads(stdout)
        logger.info(f"Successfully created identity: {json_stdout.get('id')}")
        return json_stdout

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

        stdout, _ = self._run_cmd(cmd)
        json_stdout = json.loads(stdout)
        logger.info(f"Successfully fetched identity: {identity_id}")
        return json_stdout

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

        stdout, _ = self._run_cmd(cmd)
        logger.info(f"Successfully deleted identity: {identity_id}")
        return stdout

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
        stdout, _ = self._run_cmd(cmd)
        json_stdout = json.loads(stdout)
        logger.info("Successfully fetched all identities")
        return json_stdout

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
        data = dict(identity_id=identity_id, expires_in=expires_in)

        r = requests.post(url, json=data)
        r.raise_for_status()

        return r.json()

    def recover_password_with_link(self, identity_id: str, expires_in: str = "1h") -> Dict:
        """Create a magic link for recovering an identity's password."""
        url = join(self.kratos_admin_url, "admin/recovery/link")
        data = dict(identity_id=identity_id, expires_in=expires_in)

        r = requests.post(url, json=data)
        r.raise_for_status()

        return r.json()

    def run_migration(self, timeout: float = 120) -> Tuple[str, str]:
        """Run an sql migration."""
        cmd = [
            "kratos",
            "migrate",
            "sql",
            "-e",
            "--config",
            self.config_file_path,
            "--yes",
        ]
        return self._run_cmd(cmd, timeout=timeout)

    def _run_cmd(
        self, cmd: List[str], timeout: float = 20, stdin: Optional[str] = None
    ) -> Tuple[str, str]:
        logger.debug(f"Running cmd: {cmd}")
        process = self.container.exec(cmd, timeout=timeout)
        if stdin:
            process.stdin.write(stdin)
            process.stdin.close()
        stdout, stderr = process.wait_output()

        if isinstance(stdout, bytes):
            stdout = stdout.decode()
        if isinstance(stderr, bytes):
            stderr = stderr.decode()

        return stdout, stderr
