# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from unittest.mock import MagicMock

import pytest

from clients import Identity


class TestIdentity:
    @pytest.fixture
    def mocked_client(self) -> MagicMock:
        return MagicMock()

    def test_get_client_by_identity_id(
        self,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.get_identity.return_value = {"id": "identity-id"}

        identity_client = Identity(client=mocked_client)
        identity = identity_client.get("identity-id")

        assert identity == {"id": "identity-id"}
        mocked_client.get_identity.assert_called()
        mocked_client.get_identity_by_email.assert_not_called()

    def test_get_client_by_email(
        self,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.get_identity_by_email.return_value = {"id": "identity-id"}

        identity_client = Identity(client=mocked_client)
        identity = identity_client.get(identity_id="", email="email")

        assert identity == {"id": "identity-id"}
        mocked_client.get_identity.assert_not_called()
        mocked_client.get_identity_by_email.assert_called()

    def test_reset_password(
        self,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = "identity-id"
        mocked_client.get_identity.return_value = {"id": identity_id}
        mocked_client.reset_password.return_value = {"id": identity_id}

        identity_client = Identity(client=mocked_client)
        identity = identity_client.reset_password(identity_id, password="password")

        assert identity == {"id": identity_id}
        mocked_client.get_identity.assert_called()
        mocked_client.get_identity_by_email.assert_not_called()
        mocked_client.reset_password.assert_called()
