# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import uuid
from unittest.mock import MagicMock

import pytest
from ops import testing
from pytest_mock import MockerFixture

from charm import KratosCharm
from constants import WORKLOAD_CONTAINER
from exceptions import (
    ClientRequestError,
    IdentityAlreadyExistsError,
    IdentityCredentialsNotExistError,
    IdentityNotExistsError,
    IdentitySessionsNotExistError,
    MigrationError,
    TooManyIdentitiesError,
)
from integrations import DatabaseConfig


class TestGetIdentityAction:
    @pytest.fixture
    def mocked_get_identity(self, mocker: MockerFixture) -> MagicMock:
        mocked = mocker.patch("charm.Identity.get", autospec=True)
        return mocked

    def test_when_workload_service_not_running(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_identity: MagicMock,
    ) -> None:
        mocked_workload_service_running.return_value = False

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            ctx.run(ctx.on.action(name="get-identity", params={"email": "email"}), state_in)

        mocked_get_identity.assert_not_called()

    def test_when_redundant_identifier_provided(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_identity: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed, match="Provide only one of 'identity-id' or 'email', not both"
        ):
            ctx.run(
                ctx.on.action(
                    name="get-identity", params={"email": "email", "identity-id": "identity-id"}
                ),
                state_in,
            )

        mocked_get_identity.assert_not_called()

    def test_when_input_not_provided(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_identity: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed, match="You must provide either 'identity-id' or 'email'"
        ):
            ctx.run(ctx.on.action(name="get-identity"), state_in)

        mocked_get_identity.assert_not_called()

    def test_when_identity_not_found(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_identity: MagicMock,
    ) -> None:
        mocked_get_identity.side_effect = IdentityNotExistsError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Identity not found"):
            ctx.run(ctx.on.action(name="get-identity", params={"email": "email"}), state_in)

        mocked_get_identity.assert_called()

    def test_when_too_many_identities_found(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_identity: MagicMock,
    ) -> None:
        mocked_get_identity.side_effect = TooManyIdentitiesError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Multiple identities found for email"):
            ctx.run(ctx.on.action(name="get-identity", params={"email": "email"}), state_in)

        mocked_get_identity.assert_called()

    def test_when_get_identity_failed(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_identity: MagicMock,
    ) -> None:
        mocked_get_identity.side_effect = ClientRequestError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Failed to fetch the identity"):
            ctx.run(ctx.on.action(name="get-identity", params={"email": "email"}), state_in)

        mocked_get_identity.assert_called()

    def test_when_action_succeeds(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_identity: MagicMock,
    ) -> None:
        mocked_get_identity.return_value = {"id": "identity-id"}

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(ctx.on.action(name="get-identity", params={"email": "email"}), state_in)

        mocked_get_identity.assert_called()
        assert "Successfully fetched the identity." in ctx.action_logs
        assert ctx.action_results == {"id": "identity-id"}


class TestDeleteIdentityAction:
    @pytest.fixture
    def mocked_client(self, mocker: MockerFixture) -> MagicMock:
        mocked = MagicMock()
        mocked_http_client = mocker.patch("charm.HTTPClient", autospec=True)
        mocked_http_client.return_value.__enter__.return_value = mocked
        return mocked

    def test_when_workload_service_not_running(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_workload_service_running.return_value = False

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            ctx.run(
                ctx.on.action(name="delete-identity", params={"identity-id": str(uuid.uuid4())}),
                state_in,
            )

        mocked_client.delete_identity.assert_not_called()

    def test_when_identity_not_found(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.delete_identity.side_effect = IdentityNotExistsError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Identity .* does not exist"):
            ctx.run(
                ctx.on.action(name="delete-identity", params={"identity-id": str(uuid.uuid4())}),
                state_in,
            )

        mocked_client.delete_identity.assert_called()

    def test_when_delete_identity_failed(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.delete_identity.side_effect = ClientRequestError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Failed to delete the identity"):
            ctx.run(
                ctx.on.action(name="delete-identity", params={"identity-id": str(uuid.uuid4())}),
                state_in,
            )

        mocked_client.delete_identity.assert_called()

    def test_when_action_succeeds(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = str(uuid.uuid4())

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(name="delete-identity", params={"identity-id": identity_id}),
            state_in,
        )

        mocked_client.delete_identity.assert_called()
        assert f"Successfully deleted the identity: {identity_id}" in ctx.action_logs
        assert ctx.action_results == {"id": identity_id}


class TestResetPasswordAction:
    @pytest.fixture
    def mocked_reset_password(self, mocker: MockerFixture) -> MagicMock:
        mocked = mocker.patch("charm.Identity.reset_password", autospec=True)
        return mocked

    @pytest.fixture
    def mocked_client(self, mocker: MockerFixture) -> MagicMock:
        mocked = MagicMock()
        mocked_http_client = mocker.patch("charm.HTTPClient", autospec=True)
        mocked_http_client.return_value.__enter__.return_value = mocked
        return mocked

    def test_when_workload_service_not_running(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_reset_password: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_workload_service_running.return_value = False

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            ctx.run(
                ctx.on.action(name="reset-password", params={"identity-id": str(uuid.uuid4())}),
                state_in,
            )

        mocked_reset_password.assert_not_called()
        mocked_client.create_recovery_code.assert_not_called()

    def test_when_identity_not_found(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_reset_password: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.create_recovery_code.side_effect = IdentityNotExistsError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Identity .* does not exist"):
            ctx.run(
                ctx.on.action(name="reset-password", params={"identity-id": str(uuid.uuid4())}),
                state_in,
            )

        mocked_reset_password.assert_not_called()
        mocked_client.create_recovery_code.assert_called()

    def test_when_client_request_failed(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_reset_password: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.create_recovery_code.side_effect = ClientRequestError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Failed to request Kratos API"):
            ctx.run(
                ctx.on.action(name="reset-password", params={"identity-id": str(uuid.uuid4())}),
                state_in,
            )

        mocked_reset_password.assert_not_called()
        mocked_client.create_recovery_code.assert_called()

    def test_when_password_secret_not_provided(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_reset_password: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.create_recovery_code.return_value = {
            "recovery_code": "recovery_code",
            "recovery_link": "recovery_link",
        }

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(name="reset-password", params={"identity-id": str(uuid.uuid4())}),
            state_in,
        )

        mocked_reset_password.assert_not_called()
        mocked_client.create_recovery_code.assert_called()
        assert (
            "Recovery code created successfully. Use the returned link to reset the identity's password"
            in ctx.action_logs
        )
        assert ctx.action_results == {
            "recovery-code": "recovery_code",
            "recovery-link": "recovery_link",
        }

    def test_when_password_secret_provided(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_reset_password: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = str(uuid.uuid4())
        mocked_reset_password.return_value = {"id": identity_id}

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        secret = testing.Secret(id="password_secret_id", tracked_content={"password": "password"})
        state_in = testing.State(containers={container}, secrets=[secret])

        ctx.run(
            ctx.on.action(
                name="reset-password",
                params={"identity-id": identity_id, "password-secret-id": "password_secret_id"},
            ),
            state_in,
        )

        mocked_reset_password.assert_called()
        mocked_client.create_recovery_code.assert_not_called()
        assert "Password was changed successfully" in ctx.action_logs
        assert ctx.action_results == {"id": identity_id}


class TestInvalidateIdentitySessionsAction:
    @pytest.fixture
    def mocked_client(self, mocker: MockerFixture) -> MagicMock:
        mocked = MagicMock()
        mocked_http_client = mocker.patch("charm.HTTPClient", autospec=True)
        mocked_http_client.return_value.__enter__.return_value = mocked
        return mocked

    def test_when_workload_service_not_running(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_workload_service_running.return_value = False

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            ctx.run(
                ctx.on.action(
                    name="invalidate-identity-sessions", params={"identity-id": str(uuid.uuid4())}
                ),
                state_in,
            )

        mocked_client.invalidate_sessions.assert_not_called()

    def test_when_sessions_not_found(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = str(uuid.uuid4())
        mocked_client.invalidate_sessions.side_effect = IdentitySessionsNotExistError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="invalidate-identity-sessions", params={"identity-id": identity_id}
            ),
            state_in,
        )

        mocked_client.invalidate_sessions.assert_called()
        assert f"Identity {identity_id} has no sessions" in ctx.action_logs

    def test_when_invalidate_sessions_failed(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.invalidate_sessions.side_effect = ClientRequestError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Failed to invalidate and delete sessions"):
            ctx.run(
                ctx.on.action(
                    name="invalidate-identity-sessions", params={"identity-id": str(uuid.uuid4())}
                ),
                state_in,
            )

        mocked_client.invalidate_sessions.assert_called()

    def test_when_action_succeeds(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="invalidate-identity-sessions", params={"identity-id": str(uuid.uuid4())}
            ),
            state_in,
        )

        mocked_client.invalidate_sessions.assert_called()
        assert "Successfully invalidated and deleted the sessions" in ctx.action_logs


class TestCreateAdminAccountAction:
    @pytest.fixture
    def mocked_client(self, mocker: MockerFixture) -> MagicMock:
        mocked = MagicMock()
        mocked_http_client = mocker.patch("charm.HTTPClient", autospec=True)
        mocked_http_client.return_value.__enter__.return_value = mocked
        return mocked

    def test_when_workload_service_not_running(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_workload_service_running.return_value = False

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            ctx.run(
                ctx.on.action(
                    name="create-admin-account",
                    params={
                        "username": "username",
                        "email": "email",
                        "name": "name",
                        "phone-number": "phone_number",
                    },
                ),
                state_in,
            )

        mocked_client.create_identity.assert_not_called()
        mocked_client.create_recovery_code.assert_not_called()

    def test_when_account_exists(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.create_identity.side_effect = IdentityAlreadyExistsError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="The account already exists"):
            ctx.run(
                ctx.on.action(
                    name="create-admin-account",
                    params={
                        "username": "username",
                        "email": "email",
                        "name": "name",
                        "phone-number": "phone_number",
                    },
                ),
                state_in,
            )

        mocked_client.create_identity.assert_called()
        mocked_client.create_recovery_code.assert_not_called()

    def test_when_client_request_failed(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.create_identity.side_effect = ClientRequestError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Failed to create the admin account"):
            ctx.run(
                ctx.on.action(
                    name="create-admin-account",
                    params={
                        "username": "username",
                        "email": "email",
                        "name": "name",
                        "phone-number": "phone_number",
                    },
                ),
                state_in,
            )

        mocked_client.create_identity.assert_called()
        mocked_client.create_recovery_code.assert_not_called()

    def test_when_password_secret_not_provided(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.create_identity.return_value = {"id": "identity-id"}
        mocked_client.create_recovery_code.return_value = {
            "recovery_code": "recovery_code",
            "recovery_link": "recovery_link",
        }

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="create-admin-account",
                params={
                    "username": "username",
                    "email": "email",
                    "name": "name",
                    "phone-number": "phone_number",
                },
            ),
            state_in,
        )

        mocked_client.create_identity.assert_called()
        mocked_client.create_recovery_code.assert_called()
        assert "Successfully created the admin account: identity-id" in ctx.action_logs
        assert ctx.action_results == {
            "identity-id": "identity-id",
            "recovery-code": "recovery_code",
            "recovery-link": "recovery_link",
        }

    def test_when_password_secret_provided(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.create_identity.return_value = {"id": "identity-id"}
        mocked_client.create_recovery_code.return_value = {
            "recovery_code": "recovery_code",
            "recovery_link": "recovery_link",
        }

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        secret = testing.Secret(id="password_secret_id", tracked_content={"password": "password"})
        state_in = testing.State(containers={container}, secrets=[secret])

        ctx.run(
            ctx.on.action(
                name="create-admin-account",
                params={
                    "username": "username",
                    "email": "email",
                    "name": "name",
                    "phone-number": "phone_number",
                    "password-secret-id": "password_secret_id",
                },
            ),
            state_in,
        )

        mocked_client.create_identity.assert_called()
        mocked_client.create_recovery_code.assert_not_called()
        assert "Successfully created the admin account: identity-id" in ctx.action_logs
        assert ctx.action_results == {"identity-id": "identity-id"}


class TestListOIDCAccountsAction:
    @pytest.fixture
    def mocked_get_oidc_identifiers(self, mocker: MockerFixture) -> MagicMock:
        mocked = mocker.patch("charm.Identity.get_oidc_identifiers", autospec=True)
        return mocked

    def test_when_workload_service_not_running(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_oidc_identifiers: MagicMock,
    ) -> None:
        mocked_workload_service_running.return_value = False

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            ctx.run(
                ctx.on.action(
                    name="list-oidc-accounts", params={"identity-id": str(uuid.uuid4())}
                ),
                state_in,
            )

        mocked_get_oidc_identifiers.assert_not_called()

    def test_when_identity_not_found(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_oidc_identifiers: MagicMock,
    ) -> None:
        mocked_get_oidc_identifiers.side_effect = IdentityNotExistsError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(testing.ActionFailed, match="Identity .* does not exist"):
            ctx.run(
                ctx.on.action(
                    name="list-oidc-accounts",
                    params={"identity-id": str(uuid.uuid4())},
                ),
                state_in,
            )

        mocked_get_oidc_identifiers.assert_called()

    def test_when_get_identity_failed(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_oidc_identifiers: MagicMock,
    ) -> None:
        mocked_get_oidc_identifiers.side_effect = ClientRequestError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Failed to fetch the identity OIDC credentials for .*",
        ):
            ctx.run(
                ctx.on.action(
                    name="list-oidc-accounts",
                    params={"identity-id": str(uuid.uuid4())},
                ),
                state_in,
            )

        mocked_get_oidc_identifiers.assert_called()

    def test_when_oidc_credentials_not_exist(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_oidc_identifiers: MagicMock,
    ) -> None:
        mocked_get_oidc_identifiers.return_value = []

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="list-oidc-accounts",
                params={"identity-id": str(uuid.uuid4())},
            ),
            state_in,
        )

        assert "Identity OIDC credentials not found" in ctx.action_logs
        mocked_get_oidc_identifiers.assert_called()

    def test_when_action_succeeds(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_get_oidc_identifiers: MagicMock,
    ) -> None:
        mocked_get_oidc_identifiers.return_value = ["identifier_one", "identifier_two"]

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="list-oidc-accounts",
                params={"identity-id": str(uuid.uuid4())},
            ),
            state_in,
        )

        mocked_get_oidc_identifiers.assert_called()
        assert "Successfully fetched the identity OIDC credentials" in ctx.action_logs
        assert ctx.action_results == {"identifiers": "identifier_one\nidentifier_two"}


class TestUnlinkOIDCAccountAction:
    @pytest.fixture
    def mocked_client(self, mocker: MockerFixture) -> MagicMock:
        mocked = MagicMock()
        mocked_http_client = mocker.patch("charm.HTTPClient", autospec=True)
        mocked_http_client.return_value.__enter__.return_value = mocked
        return mocked

    def test_when_workload_service_not_running(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_workload_service_running.return_value = False

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            ctx.run(
                ctx.on.action(
                    name="unlink-oidc-account",
                    params={"identity-id": str(uuid.uuid4()), "credential-id": "credential-id"},
                ),
                state_in,
            )

        mocked_client.delete_mfa_credential.assert_not_called()

    def test_when_credential_not_exist(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = str(uuid.uuid4())
        mocked_client.delete_mfa_credential.side_effect = IdentityCredentialsNotExistError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="unlink-oidc-account",
                params={"identity-id": identity_id, "credential-id": "credential-id"},
            ),
            state_in,
        )

        assert f"Identity {identity_id} has no oidc credentials" in ctx.action_logs
        mocked_client.delete_mfa_credential.assert_called()

    def test_when_delete_credential_failed(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.delete_mfa_credential.side_effect = ClientRequestError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Failed to delete the oidc credentials",
        ):
            ctx.run(
                ctx.on.action(
                    name="unlink-oidc-account",
                    params={"identity-id": str(uuid.uuid4()), "credential-id": "credential-id"},
                ),
                state_in,
            )

        mocked_client.delete_mfa_credential.assert_called()

    def test_when_action_succeeds(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = str(uuid.uuid4())

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="unlink-oidc-account",
                params={"identity-id": identity_id, "credential-id": "credential-id"},
            ),
            state_in,
        )

        assert (
            f"Successfully unlink the oidc account for identity {identity_id}" in ctx.action_logs
        )
        mocked_client.delete_mfa_credential.assert_called()


class TestResetIdentityMFAAction:
    @pytest.fixture
    def mocked_client(self, mocker: MockerFixture) -> MagicMock:
        mocked = MagicMock()
        mocked_http_client = mocker.patch("charm.HTTPClient", autospec=True)
        mocked_http_client.return_value.__enter__.return_value = mocked
        return mocked

    def test_when_workload_service_not_running(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_workload_service_running.return_value = False

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Service is not ready. Please re-run the action when the charm is active",
        ):
            ctx.run(
                ctx.on.action(
                    name="reset-identity-mfa",
                    params={"identity-id": str(uuid.uuid4()), "mfa-type": "totp"},
                ),
                state_in,
            )

        mocked_client.delete_mfa_credential.assert_not_called()

    def test_when_credential_type_not_supported(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = str(uuid.uuid4())

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed, match="Unsupported MFA credential type lookupsecret"
        ):
            ctx.run(
                ctx.on.action(
                    name="reset-identity-mfa",
                    params={"identity-id": identity_id, "mfa-type": "lookupsecret"},
                ),
                state_in,
            )

        mocked_client.delete_mfa_credential.assert_not_called()

    def test_when_credential_not_exist(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = str(uuid.uuid4())
        mocked_client.delete_mfa_credential.side_effect = IdentityCredentialsNotExistError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="reset-identity-mfa",
                params={"identity-id": identity_id, "mfa-type": "totp"},
            ),
            state_in,
        )

        assert f"Identity {identity_id} has no totp credentials." in ctx.action_logs
        mocked_client.delete_mfa_credential.assert_called()

    def test_when_delete_credential_failed(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        mocked_client.delete_mfa_credential.side_effect = ClientRequestError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        with pytest.raises(
            testing.ActionFailed,
            match="Failed to reset the totp credentials",
        ):
            ctx.run(
                ctx.on.action(
                    name="reset-identity-mfa",
                    params={"identity-id": str(uuid.uuid4()), "mfa-type": "totp"},
                ),
                state_in,
            )

        mocked_client.delete_mfa_credential.assert_called()

    def test_when_action_succeeds(
        self,
        mocked_workload_service_running: MagicMock,
        mocked_client: MagicMock,
    ) -> None:
        identity_id = str(uuid.uuid4())

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        ctx.run(
            ctx.on.action(
                name="reset-identity-mfa",
                params={"identity-id": identity_id, "mfa-type": "totp"},
            ),
            state_in,
        )

        assert (
            f"Successfully reset the totp credentials for identity {identity_id}"
            in ctx.action_logs
        )
        mocked_client.delete_mfa_credential.assert_called()


class TestRunMigrationAction:
    @pytest.fixture(autouse=True)
    def mocked_database_config(self, mocker: MockerFixture) -> DatabaseConfig:
        mocked = mocker.patch(
            "charm.DatabaseConfig.load",
            return_value=DatabaseConfig(migration_version="migration_version_0"),
        )
        return mocked.return_value

    @pytest.fixture
    def mocked_cli(self, mocker: MockerFixture) -> MagicMock:
        return mocker.patch("charm.CommandLine.migrate")

    def test_when_container_not_connected(
        self,
        mocked_cli: MagicMock,
        peer_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(leader=True, containers={container}, relations={peer_integration})

        with pytest.raises(
            testing.ActionFailed,
            match="Container is not connected yet",
        ):
            ctx.run(ctx.on.action(name="run-migration"), state_in)

        mocked_cli.assert_not_called()

    def test_when_peer_integration_not_exist(
        self,
        mocked_cli: MagicMock,
        mocked_workload_service_running: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(leader=True, containers={container})

        with pytest.raises(testing.ActionFailed, match="Peer integration is not ready"):
            ctx.run(ctx.on.action(name="run-migration"), state_in)

        mocked_cli.assert_not_called()

    def test_when_commandline_failed(
        self,
        mocked_cli: MagicMock,
        mocked_workload_service_running: MagicMock,
        peer_integration: testing.Relation,
    ) -> None:
        mocked_cli.side_effect = MigrationError

        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(leader=True, containers={container}, relations={peer_integration})

        with pytest.raises(testing.ActionFailed, match="Database migration failed"):
            ctx.run(ctx.on.action(name="run-migration"), state_in)

        mocked_cli.assert_called()

    def test_when_action_succeeds(
        self,
        mocked_cli: MagicMock,
        mocked_workload_service_running: MagicMock,
        peer_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(leader=True, containers={container}, relations={peer_integration})

        ctx.run(ctx.on.action(name="run-migration"), state_in)

        mocked_cli.assert_called()
        assert "Successfully migrated the database" in ctx.action_logs
        assert "Successfully updated migration version" in ctx.action_logs
