# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
from types import TracebackType
from typing import Optional

import bcrypt
import requests
from typing_extensions import Self, Type

from exceptions import (
    ClientRequestError,
    IdentityCredentialsNotExistError,
    IdentityNotExistsError,
    IdentitySessionsNotExistError,
    TooManyIdentitiesError,
)

logger = logging.getLogger(__name__)


class HTTPClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.verify = False

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: TracebackType,
    ) -> None:
        self._session.close()

    def get_identity(self, identity_id: str, *, params: Optional[dict] = None) -> dict:
        """More information: https://www.ory.sh/docs/kratos/reference/api#tag/identity/operation/getIdentity."""
        try:
            resp = self._session.get(
                f"{self._base_url}/admin/identities/{identity_id}", params=params
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 404:
                raise IdentityNotExistsError

            raise ClientRequestError from err
        except requests.exceptions.RequestException:
            raise ClientRequestError

        return resp.json()

    def get_identity_by_email(self, email: str) -> dict:
        """More information: https://www.ory.sh/docs/kratos/reference/api#tag/identity/operation/listIdentities."""
        try:
            resp = self._session.get(
                f"{self._base_url}/admin/identities",
                params={"credentials_identifier": email},
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException:
            raise ClientRequestError

        if not (identities := resp.json()):
            raise IdentityNotExistsError

        if len(identities) > 1:
            raise TooManyIdentitiesError

        return identities[0]

    def create_identity(
        self, traits: dict, *, schema_id: str = "default", password: Optional[str] = None
    ) -> dict:
        """More information: https://www.ory.sh/docs/kratos/reference/api#tag/identity/operation/createIdentity."""
        identity = {"traits": traits, "schema_id": schema_id}
        if password:
            identity["credentials"] = {"password": {"config": {"password": password}}}

        try:
            resp = self._session.post(
                url=f"{self._base_url}/admin/identities",
                json=identity,
            )
            resp.raise_for_status()
        except requests.exceptions.RequestException as err:
            raise ClientRequestError from err

        return resp.json()

    def delete_identity(self, identity_id: str) -> None:
        """More information: https://www.ory.sh/docs/kratos/reference/api#tag/identity/operation/deleteIdentity."""
        try:
            resp = self._session.delete(url=f"{self._base_url}/admin/identities/{identity_id}")
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 404:
                raise IdentityNotExistsError

            raise ClientRequestError from err
        except requests.exceptions.RequestException:
            raise ClientRequestError

    def reset_password(self, identity: dict, password: str) -> dict:
        """More information: https://www.ory.sh/docs/kratos/reference/api#tag/identity/operation/updateIdentity.

        Note: passwords can't be updated with Kratos CLI
        """
        credentials = {
            "password": {
                "config": {
                    "hashed_password": bcrypt.hashpw(
                        password.encode("utf-8"), bcrypt.gensalt()
                    ).decode("utf-8")
                }
            }
        }

        data = {
            "state": identity.get("state"),
            "traits": identity.get("traits"),
            "schema_id": identity.get("schema_id"),
            "credentials": credentials,
        }
        try:
            resp = self._session.put(
                f"{self._base_url}/admin/identities/{identity['id']}", json=data
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            logger.error("Failed to update the identity's password: %s", err)
            if err.response.status_code == 404:
                raise IdentityNotExistsError

            raise ClientRequestError from err
        except requests.exceptions.RequestException:
            raise ClientRequestError

        return resp.json()

    def create_recovery_code(self, identity_id: str, expires_in: str = "1h") -> dict:
        """More information: https://www.ory.sh/docs/kratos/reference/api#tag/identity/operation/createRecoveryCodeForIdentity."""
        data = {"identity_id": identity_id, "expires_in": expires_in}

        try:
            resp = self._session.post(f"{self._base_url}/admin/recovery/code", json=data)
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 404:
                raise IdentityNotExistsError

            raise ClientRequestError from err
        except requests.exceptions.RequestException:
            raise ClientRequestError

        return resp.json()

    def delete_mfa_credential(
        self, identity_id: str, mfa_type: str, *, params: Optional[dict] = None
    ) -> None:
        """More information: https://www.ory.sh/docs/kratos/reference/api#tag/identity/operation/deleteIdentityCredentials."""
        try:
            resp = self._session.delete(
                f"{self._base_url}/admin/identities/{identity_id}/credentials/{mfa_type}",
                params=params,
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 404:
                raise IdentityCredentialsNotExistError

            raise ClientRequestError from err
        except requests.exceptions.RequestException:
            raise ClientRequestError

    def invalidate_sessions(self, identity_id: str) -> None:
        """More information: https://www.ory.sh/docs/kratos/reference/api#tag/identity/operation/deleteIdentitySessions."""
        try:
            resp = self._session.delete(
                f"{self._base_url}/admin/identities/{identity_id}/sessions"
            )
            resp.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response.status_code == 404:
                raise IdentitySessionsNotExistError

            raise ClientRequestError from err
        except requests.exceptions.RequestException:
            raise ClientRequestError


class Identity:
    def __init__(self, client: HTTPClient) -> None:
        self._client = client

    def get(self, identity_id: str, email: Optional[str] = None) -> dict:
        if email:
            return self._client.get_identity_by_email(email)

        return self._client.get_identity(identity_id)

    def reset_password(self, identity_id: str, password: str) -> dict:
        identity = self.get(identity_id)
        return self._client.reset_password(identity, password)

    def get_oidc_identifiers(self, identity_id: str) -> list[str]:
        identity = self._client.get_identity(
            identity_id,
            params={"include_credential": "oidc"},
        )
        oidc_creds = identity.get("credentials", {}).get("oidc", {})
        return oidc_creds.get("identifiers", [])
