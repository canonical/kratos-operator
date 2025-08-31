# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import hashlib
import json
import logging
from abc import ABC, abstractmethod
from collections import ChainMap
from json import JSONDecodeError
from typing import Any, Mapping, Optional, Protocol, TypeAlias

from charms.kratos_external_idp_integrator.v1.kratos_external_provider import Provider
from jinja2 import Template
from lightkube import ApiError, Client
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import ConfigMap
from ops import ConfigData, Container
from ops.pebble import PathError
from typing_extensions import Self

from constants import (
    CONFIG_FILE_PATH,
    DEFAULT_SCHEMA_ID_FILE_NAME,
    EMAIL_TEMPLATE_FILE_PATH,
    IDENTITY_SCHEMAS_LOCAL_DIR_PATH,
    MAPPERS_LOCAL_DIR_PATH,
    PROVIDERS_CONFIGMAP_FILE_NAME,
)
from env_vars import EnvVars
from exceptions import ConfigMapError

ServiceConfigs: TypeAlias = Mapping[str, Any]

logger = logging.getLogger(__name__)


class ServiceConfigSource(Protocol):
    """An interface enforcing the contribution to workload service configs."""

    def to_service_configs(self) -> ServiceConfigs:
        pass


class ConfigFile:
    """An abstraction of the workload service configuration file."""

    def __init__(self, content: str) -> None:
        self.content = content

    @classmethod
    def from_sources(cls, *service_config_sources: ServiceConfigSource) -> Self:
        with open("templates/kratos.yaml.j2", "r") as file:
            template = Template(file.read())

        configs = ChainMap(*(source.to_service_configs() for source in service_config_sources))  # type: ignore

        rendered = template.render(configs)
        return cls(rendered)

    @classmethod
    def from_workload_container(cls, workload_container: Container) -> Self:
        try:
            with workload_container.pull(CONFIG_FILE_PATH, encoding="utf-8") as config_file:
                return cls(config_file.read())
        except PathError:
            return cls("")

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, ConfigFile):
            return NotImplemented

        return hash(self) == hash(other)

    def __hash__(self) -> int:
        return int(hashlib.md5(self.content.encode()).hexdigest(), 16)


class CharmConfig:
    """A class representing the data source of charm configurations."""

    def __init__(self, config: ConfigData) -> None:
        self._config = config

    def __getitem__(self, key: str) -> Any:
        return self._config.get(key)

    def to_env_vars(self) -> EnvVars:
        config_env_vars = {
            "DEV": self._config["dev"],
            "LOG_LEVEL": self._config["log_level"],
            "HTTP_PROXY": self._config["http_proxy"],
            "HTTPS_PROXY": self._config["https_proxy"],
            "NO_PROXY": self._config["no_proxy"],
        }

        if self._config.get("recovery_email_template"):
            config_env_vars["COURIER_TEMPLATES_RECOVERY_CODE_VALID_EMAIL_BODY_HTML"] = (
                f"file://{EMAIL_TEMPLATE_FILE_PATH}"
            )

        enable_local_idp = self._config["enable_local_idp"]
        enforce_mfa = self._config["enforce_mfa"]
        enable_oidc_webauthn_sequencing = self._config["enable_oidc_webauthn_sequencing"]
        if enable_oidc_webauthn_sequencing or (enable_local_idp and enforce_mfa):
            config_env_vars["SESSION_WHOAMI_REQUIRED_AAL"] = "highest_available"

        return config_env_vars

    def to_service_configs(self) -> ServiceConfigs:
        return {
            "enable_local_idp": self._config["enable_local_idp"],
            "enforce_mfa": self._config["enforce_mfa"],
            "enable_passwordless_login_method": self._config["enable_passwordless_login_method"],
            "enable_oidc_webauthn_sequencing": self._config["enable_oidc_webauthn_sequencing"],
        }


class ClaimMapper:
    """A class representing the data source of the Kratos claim mapping."""

    def to_service_configs(self) -> ServiceConfigs:
        mappers = {}
        for path in MAPPERS_LOCAL_DIR_PATH.glob("*.jsonnet"):
            try:
                content = path.read_text(encoding="utf-8")
            except OSError:
                continue

            mappers[path.stem] = self._encode(content)

        return {"mappers": mappers}

    @staticmethod
    def _encode(text: str) -> str:
        return f"base64://{base64.b64encode(text.encode('utf-8')).decode('utf-8')}"


class BaseConfigMap:
    registry: set = set()
    name: str

    def __init_subclass__(cls, **kwargs: Any):
        super().__init_subclass__(**kwargs)

        if not hasattr(cls, "name"):
            raise TypeError(f"{cls.__name__} must define a 'name' attribute")

        BaseConfigMap.registry.add(cls)

    def __init__(self, k8s_client: Client, namespace: str, app_name: str):
        self._client = k8s_client
        self.namespace = namespace
        self.app_name = app_name

    def get(self) -> Optional[dict]:
        try:
            cm = self._client.get(ConfigMap, name=self.name, namespace=self.namespace)
        except ApiError:
            return None

        if not cm.data:
            return {}

        data = {}
        for k, v in cm.data.items():
            try:
                data[k] = json.loads(v)
            except JSONDecodeError:
                data[k] = v

        return data

    def create(self) -> None:
        if self.get() is not None:
            return

        cm = ConfigMap(
            apiVersion="v1",
            kind="ConfigMap",
            metadata=ObjectMeta(
                name=self.name,
                namespace=self.namespace,
                labels={
                    "juju-app-name": self.app_name,
                    "app.kubernetes.io/managed-by": "juju",
                },
            ),
        )

        try:
            self._client.create(cm)
        except ApiError:
            logger.error("Failed to create the ConfigMap %s", self.name)
            raise ConfigMapError(f"Failed to create the ConfigMap {self.name}")

    def delete(self) -> None:
        try:
            self._client.delete(ConfigMap, name=self.name, namespace=self.namespace)
        except ApiError:
            logger.error("Failed to delete the ConfigMap %s", self.name)


class IdentitySchemaConfigMap(BaseConfigMap):
    """The ConfigMap contains the identity schemas."""

    name = "identity-schemas"

    def __init__(self, k8s_client: Client, namespace: str, app_name: str):
        super().__init__(k8s_client, namespace, app_name)


class OIDCProviderConfigMap(BaseConfigMap):
    """The ConfigMap contains the OIDC provider configurations."""

    name = "oidc-providers"

    def __init__(self, k8s_client: Client, namespace: str, app_name: str):
        super().__init__(k8s_client, namespace, app_name)

    def to_service_configs(self) -> ServiceConfigs:
        if not (providers := self.get()):
            return {
                "configmap_oidc_providers": [],
            }

        return {
            "configmap_oidc_providers": [
                Provider.model_validate(provider)
                for provider in providers[PROVIDERS_CONFIGMAP_FILE_NAME]
            ],
        }


def create_configmaps(k8s_client: Client, namespace: str, app_name: str) -> None:
    for cls in BaseConfigMap.registry:
        cls(k8s_client, namespace, app_name).create()


def remove_configmaps(k8s_client: Client, namespace: str, app_name: str) -> None:
    for cls in BaseConfigMap.registry:
        cls(k8s_client, namespace, app_name).delete()


class IdentitySchemaProvider(ABC):
    """The identity schema provider base class."""

    @abstractmethod
    def get_schemas(self) -> Optional[tuple[str, dict]]:
        pass

    @staticmethod
    def encode(schemas: dict[str, str]) -> dict[str, str]:
        return {
            schema_id: f"base64://{base64.b64encode(schema.encode()).decode()}"
            for schema_id, schema in schemas.items()
        }


class CharmConfigIdentitySchemaProvider(IdentitySchemaProvider):
    """The identity schemas provided by the charm config."""

    def __init__(self, charm_config: CharmConfig):
        self._config = charm_config

    def get_schemas(self) -> Optional[tuple[str, dict]]:
        if not (default_schema_id := self._config["default_identity_schema_id"]):
            return None

        if not (schemas := self._get_schema()):
            return None

        return default_schema_id, self.encode(schemas)

    def _get_schema(self) -> dict:
        if not (identity_schemas := self._config["identity_schemas"]):
            return {}

        try:
            schemas = json.loads(identity_schemas)
        except json.JSONDecodeError as e:
            logger.error(f"identity_schemas in charm config is not a valid json: {e}")
            return {}

        return {schema_id: json.dumps(schema) for schema_id, schema in schemas.items()}


class ConfigMapIdentitySchemaProvider(IdentitySchemaProvider):
    """The identity schemas provided by the K8s ConfigMap."""

    def __init__(self, schemas_configmap: IdentitySchemaConfigMap):
        self._schemas_configmap = schemas_configmap

    def get_schemas(self) -> Optional[tuple[str, dict]]:
        if not (identity_schemas := self._schemas_configmap.get()):
            return None

        if not (default_schema_id := identity_schemas.pop("default.schema")):
            logger.error("Identity schemas ConfigMap does not contain `default.schema`")
            return None

        return default_schema_id, self.encode(identity_schemas)


class DefaultIdentitySchemaProvider(IdentitySchemaProvider):
    """The default identity schemas provided by the local files."""

    def get_schemas(self) -> Optional[tuple[str, dict]]:
        schemas = self._get_schema()
        default_schema_id = self._get_default_schema_id()

        if default_schema_id not in schemas:
            logger.error("Default schema `%s` cannot be found", default_schema_id)
            return None

        return default_schema_id, self.encode(schemas)

    @staticmethod
    def _get_schema() -> dict:
        schemas = {}
        for schema_file in IDENTITY_SCHEMAS_LOCAL_DIR_PATH.glob("*.json"):
            try:
                schema = schema_file.read_text()
            except OSError:
                continue

            schemas[schema_file.stem] = schema

        return schemas

    @staticmethod
    def _get_default_schema_id() -> str:
        default_schema_id_file = IDENTITY_SCHEMAS_LOCAL_DIR_PATH / DEFAULT_SCHEMA_ID_FILE_NAME
        try:
            default_schema_id = default_schema_id_file.read_text()
        except OSError:
            return ""

        return default_schema_id


class IdentitySchema:
    def __init__(self, providers: list[IdentitySchemaProvider]):
        self._providers = providers

    def get_schemas(self) -> tuple[str, dict]:
        for provider in self._providers:
            if schemas := provider.get_schemas():
                return schemas

        raise RuntimeError("No valid identity schema found")

    def to_service_configs(self) -> ServiceConfigs:
        default_identity_schema_id, schemas = self.get_schemas()
        return {
            "default_identity_schema_id": default_identity_schema_id,
            "identity_schemas": schemas,
        }
