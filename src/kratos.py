# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""A helper class for interacting with the kratos API."""

import json
import logging
import re
from os.path import join
from typing import Dict, List, Optional

import bcrypt
import requests
from ops.model import Container

from constants import CONFIG_FILE_PATH
from exceptions import TooManyIdentitiesError

logger = logging.getLogger(__name__)


class KratosAPI:
    """A helper object for interacting with the kratos API."""

    def __init__(self, kratos_admin_url: str, container: Container) -> None:
        self.kratos_admin_url = kratos_admin_url
        self.container = container

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

    def get_identity_from_email(self, email: str) -> Optional[Dict]:
        """Get an identity using an email.

        This will fetch all identities and iterate over them in memory.
        """
        url = join(self.kratos_admin_url, "admin/identities")
        r = requests.get(url, {"credentials_identifier": email})
        r.raise_for_status()
        identities = r.json()
        if len(identities) > 1:
            raise TooManyIdentitiesError()
        if not identities:
            return None
        return identities[0]

    def recover_password_with_code(self, identity_id: str, expires_in: str = "1h") -> Dict:
        """Create a one time code for recovering an identity's password."""
        url = join(self.kratos_admin_url, "admin/recovery/code")
        data = {"identity_id": identity_id, "expires_in": expires_in}

        r = requests.post(url, json=data)
        r.raise_for_status()

        return r.json()

    def reset_password(self, identity_id: str, password: str) -> Dict:
        """Set identity's password to a provided value."""
        identity = self.get_identity(identity_id)
        traits = identity.get("traits")
        schema_id = identity.get("schema_id")
        state = identity.get("state")

        credentials = {
            "password": {
                "config": {
                    "hashed_password": bcrypt.hashpw(
                        password.encode("utf-8"), bcrypt.gensalt()
                    ).decode("utf-8")
                }
            }
        }

        # Update the identity with new password.
        # Note that passwords can't be updated with Kratos CLI
        url = join(self.kratos_admin_url, f"admin/identities/{identity_id}")
        data = {
            "state": state,
            "traits": traits,
            "schema_id": schema_id,
            "credentials": credentials,
        }

        r = requests.put(url, json=data)
        r.raise_for_status()

        return r.json()

    def invalidate_sessions(self, identity_id: str) -> Optional[bool]:
        """Invalidate and delete all sessions that belong to an identity."""
        url = join(self.kratos_admin_url, f"admin/identities/{identity_id}/sessions")

        try:
            r = requests.delete(url)
            # This endpoint returns 204 if sessions were deleted or 404 if the identity had no sessions
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 404:
                logger.info("No sessions found for the identity")
                return False
            raise err

        return True

    def delete_mfa_credential(self, identity_id: str, mfa_type: str) -> Optional[bool]:
        """Delete a second factor credential of an identity."""
        url = join(self.kratos_admin_url, f"admin/identities/{identity_id}/credentials/{mfa_type}")

        try:
            r = requests.delete(url)
            # This endpoint returns 204 if credentials were deleted or 404 if the identity had no credentials
            # of the selected type
            r.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 404:
                logger.info("No credentials found for the identity")
                return False
            raise err

        return True

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
            cmd.append(CONFIG_FILE_PATH)
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
