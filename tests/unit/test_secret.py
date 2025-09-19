# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, create_autospec

import pytest
from ops import Model, SecretNotFoundError

from constants import (
    COOKIE_SECRET_CONTENT_KEY,
    COOKIE_SECRET_LABEL,
)
from secret import Secrets


class TestSecrets:
    @pytest.fixture
    def mocked_model(self) -> MagicMock:
        return create_autospec(Model)

    @pytest.fixture
    def secrets(self, mocked_model: MagicMock) -> Secrets:
        return Secrets(mocked_model)

    def test_get(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_secret = MagicMock()
        mocked_secret.get_content.return_value = {COOKIE_SECRET_CONTENT_KEY: "cookie"}
        mocked_model.get_secret.return_value = mocked_secret

        content = secrets[COOKIE_SECRET_LABEL]
        assert content == {COOKIE_SECRET_CONTENT_KEY: "cookie"}

    def test_get_with_invalid_label(self, secrets: Secrets) -> None:
        content = secrets["invalid_label"]
        assert content is None

    def test_get_with_secret_not_found(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_model.get_secret.side_effect = SecretNotFoundError()

        content = secrets[COOKIE_SECRET_LABEL]
        assert content is None

    def test_set(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        content = {COOKIE_SECRET_CONTENT_KEY: "cookie"}
        secrets[COOKIE_SECRET_LABEL] = {COOKIE_SECRET_CONTENT_KEY: "cookie"}

        mocked_model.app.add_secret.assert_called_once_with(content, label=COOKIE_SECRET_LABEL)

    def test_set_with_invalid_label(self, secrets: Secrets) -> None:
        with pytest.raises(ValueError):
            secrets["invalid_label"] = {COOKIE_SECRET_CONTENT_KEY: "cookie"}

    def test_values(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_secret = MagicMock()
        mocked_secret.get_content.return_value = {COOKIE_SECRET_CONTENT_KEY: "cookie"}
        mocked_model.get_secret.return_value = mocked_secret

        actual = list(secrets.values())
        assert actual == [{COOKIE_SECRET_CONTENT_KEY: "cookie"}]

    def test_values_without_secret_found(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_model.get_secret.side_effect = SecretNotFoundError

        actual = list(secrets.values())
        assert not actual

    def test_to_env_vars(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_secret = MagicMock()
        mocked_secret.get_content.return_value = {COOKIE_SECRET_CONTENT_KEY: "cookie"}
        mocked_model.get_secret.return_value = mocked_secret

        assert secrets.to_env_vars() == {"SECRETS_COOKIE": json.dumps(["cookie"])}

    def test_is_ready(self, mocked_model: MagicMock, secrets: Secrets) -> None:
        mocked_secret = MagicMock()
        mocked_secret.get_content.return_value = {COOKIE_SECRET_CONTENT_KEY: "cookie"}
        mocked_model.get_secret.return_value = mocked_secret

        assert secrets.is_ready is True

    def test_is_ready_without_secret_found(
        self, mocked_model: MagicMock, secrets: Secrets
    ) -> None:
        mocked_model.get_secret.side_effect = SecretNotFoundError
        assert secrets.is_ready is False
