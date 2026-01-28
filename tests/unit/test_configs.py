# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
import base64
import json
from unittest.mock import MagicMock, create_autospec, patch

import httpx
import pytest
from charms.kratos_external_idp_integrator.v1.kratos_external_provider import BaseProvider
from httpx import Response
from lightkube import ApiError, Client
from lightkube.models.meta_v1 import ObjectMeta, OwnerReference
from lightkube.resources.core_v1 import ConfigMap

from configs import (
    BaseConfigMap,
    CharmConfig,
    CharmConfigIdentitySchemaProvider,
    ClaimMapper,
    ConfigMapIdentitySchemaProvider,
    IdentitySchema,
    IdentitySchemaConfigMap,
    IdentitySchemaProvider,
    OIDCProviderConfigMap,
)
from constants import EMAIL_TEMPLATE_FILE_PATH, PROVIDERS_CONFIGMAP_FILE_NAME
from exceptions import ConfigMapError


class TestCharmConfig:
    @pytest.fixture
    def mocked_config(self) -> dict:
        return {
            "dev": "true",
            "log_level": "debug",
            "http_proxy": "http://proxy",
            "https_proxy": "https://proxy",
            "no_proxy": "localhost,127.0.0.1",
            "recovery_email_template": None,
            "enable_local_idp": False,
            "enforce_mfa": False,
            "enable_passwordless_login_method": True,
            "enable_oidc_webauthn_sequencing": False,
        }

    def test_get(self, mocked_config: dict) -> None:
        charm_config = CharmConfig(mocked_config)

        assert charm_config["dev"] == "true"
        assert charm_config["log_level"] == "debug"

    def test_to_env_vars(self, mocked_config: dict) -> None:
        charm_config = CharmConfig(mocked_config)
        env_vars = charm_config.to_env_vars()

        assert env_vars["DEV"] == "true"
        assert env_vars["LOG_LEVEL"] == "debug"
        assert env_vars["HTTP_PROXY"] == "http://proxy"
        assert env_vars["HTTPS_PROXY"] == "https://proxy"
        assert env_vars["NO_PROXY"] == "localhost,127.0.0.1"
        assert "COURIER_TEMPLATES_RECOVERY_CODE_VALID_EMAIL_BODY_HTML" not in env_vars
        assert "SESSION_WHOAMI_REQUIRED_AAL" not in env_vars

    def test_to_env_vars_when_recovery_template_enabled(self, mocked_config: dict) -> None:
        mocked_config["recovery_email_template"] = "some-template"
        charm_config = CharmConfig(mocked_config)
        env_vars = charm_config.to_env_vars()

        assert env_vars["COURIER_TEMPLATES_RECOVERY_CODE_VALID_EMAIL_BODY_HTML"] == (
            f"file://{EMAIL_TEMPLATE_FILE_PATH}"
        )

    def test_to_env_vars_when_oidc_webauthn_sequencing_enabled(self, mocked_config: dict) -> None:
        mocked_config["enable_oidc_webauthn_sequencing"] = True
        charm_config = CharmConfig(mocked_config)
        env_vars = charm_config.to_env_vars()

        assert env_vars["SESSION_WHOAMI_REQUIRED_AAL"] == "highest_available"

    def test_to_env_vars_when_local_idp_and_mfa_enabled(self, mocked_config: dict) -> None:
        mocked_config["enable_local_idp"] = True
        mocked_config["enforce_mfa"] = True
        charm_config = CharmConfig(mocked_config)
        env_vars = charm_config.to_env_vars()

        assert env_vars["SESSION_WHOAMI_REQUIRED_AAL"] == "highest_available"

    def test_to_service_configs(self, mocked_config: dict) -> None:
        charm_config = CharmConfig(mocked_config)
        service_configs = charm_config.to_service_configs()

        assert service_configs == {
            "enable_local_idp": False,
            "enforce_mfa": False,
            "enable_passwordless_login_method": True,
            "enable_oidc_webauthn_sequencing": False,
        }


class TestClaimMappers:
    def test_to_service_configs(self) -> None:
        mapper = ClaimMapper()
        mappers = mapper.to_service_configs()["mappers"]

        assert "microsoft" in mappers
        assert "default" in mappers
        assert len(mappers) == 2


class TestBaseConfigMap:
    @pytest.fixture
    def mocked_client(self) -> MagicMock:
        return create_autospec(Client)

    def test_subclass_without_name(self) -> None:
        with pytest.raises(TypeError):

            class BadConfigMap(BaseConfigMap):
                pass

    def test_subclass_with_name(self) -> None:
        class GoodConfigMap(BaseConfigMap):
            name = "name"

        assert GoodConfigMap in BaseConfigMap.registry

    def test_get_cm_when_failed(self, mocked_client: MagicMock) -> None:
        mocked_client.get.side_effect = ApiError(
            response=Response(
                status_code=httpx.codes.BAD_REQUEST, content=json.dumps({"message": "bad request"})
            ),
        )

        class TestConfigMap(BaseConfigMap):
            name = "test"

        cm = TestConfigMap(mocked_client, "namespace", "app")
        actual = cm.get()

        assert actual is None

    def test_get_cm_when_no_data(self, mocked_client: MagicMock) -> None:
        mocked_cm = MagicMock()
        mocked_cm.data = None
        mocked_client.get.return_value = mocked_cm

        class TestConfigMap(BaseConfigMap):
            name = "test"

        cm = TestConfigMap(mocked_client, "namespace", "app")
        actual = cm.get()

        assert actual == {}

    def test_get_cm(self, mocked_client: MagicMock) -> None:
        mocked_cm = MagicMock()
        mocked_cm.data = {
            "valid": json.dumps({"x": 1}),
            "invalid": "{invalid json}",
        }
        mocked_client.get.return_value = mocked_cm

        class TestConfigMap(BaseConfigMap):
            name = "test"

        cm = TestConfigMap(mocked_client, "namespace", "app")
        actual = cm.get()

        assert actual["valid"] == {"x": 1}
        assert actual["invalid"] == "{invalid json}"

    def test_create_patch_owner_refs_when_configmap_exists(self, mocked_client: MagicMock) -> None:
        class TestConfigMap(BaseConfigMap):
            name = "test"

        mock_sts = MagicMock()
        mock_sts.metadata.uid = "sts-uid"
        mock_sts.metadata.name = "sts-name"
        mock_sts.apiVersion = "apps/v1"
        mock_sts.kind = "StatefulSet"

        mocked_client.get.return_value = mock_sts

        cm = TestConfigMap(mocked_client, "namespace", "app")
        cm.get = MagicMock(return_value={"already": "exists"})

        cm.create()

        mocked_client.create.assert_not_called()

        expected_patch = ConfigMap(
            metadata=ObjectMeta(
                ownerReferences=[
                    OwnerReference(
                        apiVersion="apps/v1",
                        kind="StatefulSet",
                        name="sts-name",
                        uid="sts-uid",
                        blockOwnerDeletion=True,
                        controller=True,
                    )
                ]
            )
        )
        mocked_client.patch.assert_called_once_with(
            ConfigMap, name="test", namespace="namespace", obj=expected_patch
        )

    def test_create_when_configmap_exists(self, mocked_client: MagicMock) -> None:
        class TestConfigMap(BaseConfigMap):
            name = "test"

        cm = TestConfigMap(mocked_client, "namespace", "app")
        cm.get = MagicMock(return_value={"already": "exists"})

        cm.create()

        mocked_client.create.assert_not_called()

    def test_create_when_failed(self, mocked_client: MagicMock) -> None:
        mocked_client.create.side_effect = ApiError(
            response=Response(
                status_code=httpx.codes.BAD_REQUEST, content=json.dumps({"message": "bad request"})
            ),
        )

        class TestConfigMap(BaseConfigMap):
            name = "test"

        cm = TestConfigMap(mocked_client, "namespace", "app")
        cm.get = MagicMock(return_value=None)

        with pytest.raises(ConfigMapError):
            cm.create()

    def test_patch_cm(self, mocked_client: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        class TestConfigMap(BaseConfigMap):
            name = "test"

        cm = TestConfigMap(mocked_client, "namespace", "app")
        patch_data = {"metadata": {"labels": {"new": "label"}}}

        cm.patch(patch_data)

        mocked_client.patch.assert_called_once_with(
            ConfigMap, name="test", namespace="namespace", obj=patch_data
        )
        assert "Patched ConfigMap test" in caplog.text

    def test_patch_when_api_failure(self, mocked_client: MagicMock, caplog: pytest.LogCaptureFixture) -> None:
        mocked_client.patch.side_effect = ApiError(
            response=Response(
                status_code=httpx.codes.BAD_REQUEST, content=json.dumps({"message": "bad request"})
            ),
        )

        class TestConfigMap(BaseConfigMap):
            name = "test"

        cm = TestConfigMap(mocked_client, "namespace", "app")

        cm.patch({"some": "patch"})

        assert "Failed to patch test" in caplog.text

    def test_delete_when_failed(
        self, mocked_client: MagicMock, caplog: pytest.LogCaptureFixture
    ) -> None:
        mocked_client.delete.side_effect = ApiError(
            response=Response(
                status_code=httpx.codes.BAD_REQUEST, content=json.dumps({"message": "bad request"})
            ),
        )

        class TestConfigMap(BaseConfigMap):
            name = "test"

        cm = TestConfigMap(mocked_client, "ns", "app")

        cm.delete()

        assert "Failed to delete the ConfigMap test" in caplog.text

    def test_delete_cm(self, mocked_client: MagicMock) -> None:
        class TestCM(BaseConfigMap):
            name = "test"

        cm = TestCM(mocked_client, "namespace", "app")

        cm.delete()

        mocked_client.delete.assert_called_once_with(ConfigMap, name="test", namespace="namespace")


class TestOIDCProviderConfigMap:
    @pytest.fixture
    def mocked_client(self) -> MagicMock:
        return create_autospec(Client)

    def test_to_service_configs_when_no_providers(self, mocked_client: MagicMock) -> None:
        cm = OIDCProviderConfigMap(mocked_client, "namespace", "app")
        cm.get = MagicMock(return_value=None)

        actual = cm.to_service_configs()

        assert actual == {"configmap_oidc_providers": []}

    def test_to_service_configs(self, mocked_client: MagicMock) -> None:
        provider_data = [
            {"provider": "microsoft", "client_id": "microsoft"},
            {"provider": "github", "client_id": "github"},
        ]

        cm = OIDCProviderConfigMap(mocked_client, "namespace", "app")
        cm.get = MagicMock(return_value={PROVIDERS_CONFIGMAP_FILE_NAME: provider_data})

        with patch("configs.Provider") as mocked_provider:
            mocked_provider.model_validate.side_effect = lambda x: BaseProvider.model_validate(x)

            actual = cm.to_service_configs()

        assert "configmap_oidc_providers" in actual
        assert len(actual["configmap_oidc_providers"]) == 2


class TestCharmConfigIdentitySchemaProvider:
    @pytest.fixture
    def mocked_charm_config(self) -> dict:
        return {
            "default_identity_schema_id": "default",
            "identity_schemas": json.dumps({"default": {"type": "object"}}),
        }

    def test_get_schemas_without_default_schema_id(self, mocked_charm_config: dict) -> None:
        mocked_charm_config["default_identity_schema_id"] = ""

        provider = CharmConfigIdentitySchemaProvider(mocked_charm_config)
        actual = provider.get_schemas()

        assert actual is None

    def test_get_schemas_without_identity_schemas(self, mocked_charm_config: dict) -> None:
        mocked_charm_config["identity_schemas"] = ""

        provider = CharmConfigIdentitySchemaProvider(mocked_charm_config)
        actual = provider.get_schemas()

        assert actual is None

    def test_get_schemas_with_valid_schemas(self, mocked_charm_config: MagicMock) -> None:
        provider = CharmConfigIdentitySchemaProvider(mocked_charm_config)

        default_schema_id, schemas = provider.get_schemas()

        assert default_schema_id == "default"
        decoded = base64.b64decode(schemas["default"].removeprefix("base64://")).decode()
        assert json.loads(decoded) == {"type": "object"}

    def test_get_schemas_with_invalid_schemas(self, mocked_charm_config: MagicMock) -> None:
        mocked_charm_config["identity_schemas"] = "{invalid json}"

        provider = CharmConfigIdentitySchemaProvider(mocked_charm_config)
        actual = provider.get_schemas()

        assert actual is None


class TestConfigMapIdentitySchemaProvider:
    @pytest.fixture
    def mocked_configmap(self) -> MagicMock:
        return create_autospec(IdentitySchemaConfigMap)

    def test_get_schemas_when_configmap_empty(self, mocked_configmap: MagicMock) -> None:
        mocked_configmap.get.return_value = None

        provider = ConfigMapIdentitySchemaProvider(mocked_configmap)
        actual = provider.get_schemas()

        assert actual is None
        mocked_configmap.get.assert_called_once()

    def test_get_schemas_when_default_schema_missing(self, mocked_configmap: MagicMock) -> None:
        mocked_configmap.get.return_value = {"schema": '{"type": "object"}'}

        provider = ConfigMapIdentitySchemaProvider(mocked_configmap)
        actual = provider.get_schemas()

        assert actual is None

    def test_get_schemas(self, mocked_configmap: MagicMock) -> None:
        default_schema_id = "default"
        schema = '{"type":"object"}'

        mocked_configmap.get.return_value = {
            "default.schema": default_schema_id,
            "default": schema,
        }
        provider = ConfigMapIdentitySchemaProvider(mocked_configmap)

        actual = provider.get_schemas()

        default_id, schemas = actual
        assert default_id == default_schema_id

        decoded = base64.b64decode(schemas["default"].removeprefix("base64://")).decode()
        assert json.loads(decoded) == {"type": "object"}


class TestIdentitySchema:
    @pytest.fixture
    def mocked_provider(self) -> MagicMock:
        return create_autospec(IdentitySchemaProvider)

    @pytest.fixture
    def mocked_provider_two(self) -> MagicMock:
        return create_autospec(IdentitySchemaProvider)

    def test_get_schemas(self, mocked_provider: MagicMock, mocked_provider_two: MagicMock) -> None:
        mocked_provider.get_schemas.return_value = None
        mocked_provider_two.get_schemas.return_value = ("default", {"default": "encoded_schema"})
        identity_schema = IdentitySchema([mocked_provider, mocked_provider_two])

        actual = identity_schema.get_schemas()

        assert actual == ("default", {"default": "encoded_schema"})
        mocked_provider.get_schemas.assert_called_once()
        mocked_provider_two.get_schemas.assert_called_once()

    def test_get_schemas_when_all_providers_failed(
        self, mocked_provider: MagicMock, mocked_provider_two: MagicMock
    ) -> None:
        mocked_provider.get_schemas.return_value = None
        mocked_provider_two.get_schemas.return_value = None
        identity_schema = IdentitySchema([mocked_provider, mocked_provider_two])

        with pytest.raises(RuntimeError, match="No valid identity schema found"):
            identity_schema.get_schemas()

    def test_to_service_configs(
        self, mocked_provider: MagicMock, mocked_provider_two: MagicMock
    ) -> None:
        mocked_provider.get_schemas.return_value = None
        mocked_provider_two.get_schemas.return_value = ("default", {"default": "encoded_schema"})
        schema = IdentitySchema([mocked_provider, mocked_provider_two])

        result = schema.to_service_configs()

        assert result == {
            "default_identity_schema_id": "default",
            "identity_schemas": {"default": "encoded_schema"},
        }
