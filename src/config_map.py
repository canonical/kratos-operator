# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""A helper class for managing the configMaps holding the kratos config."""

import logging
from typing import Dict

from lightkube import ApiError, Client
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import ConfigMap
from ops.charm import CharmBase

logger = logging.getLogger(__name__)


class ConfigMapManager:
    """A helper object for managing the configMaps holding the kratos config."""

    def __init__(self) -> None:
        self.configmaps = []

    def create_all(self) -> None:
        """Create all the configMaps."""
        for cm in self.configmaps:
            cm.create()

    def delete_all(self) -> None:
        """Delete all the configMaps."""
        for cm in self.configmaps:
            cm.delete()

    def register(self, cm: "BaseConfigMap") -> None:
        """Register a configMap."""
        self.configmaps.append(cm)


class BaseConfigMap:
    """Base class for managing a configMap."""

    def __init__(
        self, configmap_name: str, manager: ConfigMapManager, client: Client, charm: CharmBase
    ) -> None:
        self.name = configmap_name
        self._manager = manager
        self._client = client
        self._charm = charm
        manager.register(self)

    def create(self):
        """Create the configMap."""
        try:
            self._client.get(ConfigMap, self.name, namespace=self._charm.model.name)
            return
        except ApiError:
            pass

        cm = ConfigMap(
            apiVersion="v1",
            kind="ConfigMap",
            # TODO @nsklikas: revisit labels
            metadata=ObjectMeta(
                name=self.name,
                labels={
                    "juju-app-name": self._charm.app.name,
                    "app.kubernetes.io/managed-by": "juju",
                },
            ),
        )
        self._client.create(cm)

    def update(self, data: Dict):
        """Update the configMap."""
        try:
            cm = self._client.get(ConfigMap, self.name, namespace=self._charm.model.name)
        except ApiError:
            return
        cm.data = data
        self._client.replace(cm)

    def get(self):
        """Get the configMap."""
        try:
            cm = self._client.get(ConfigMap, self.name, namespace=self._charm.model.name)
        except ApiError:
            return {}
        return cm.data

    def delete(self):
        """Delete the configMap."""
        try:
            self._client.delete(ConfigMap, self.name, namespace=self._charm.model.name)
        except ApiError:
            raise ValueError


class KratosConfigMap(BaseConfigMap):
    """Class for managing the Kratos config configMap."""

    def __init__(self, manager: ConfigMapManager, client: Client, charm: CharmBase) -> None:
        super().__init__("kratos-config", manager, client, charm)


class IdentitySchemaConfigMap(BaseConfigMap):
    """Class for managing the Identity Schemas configMap."""

    def __init__(self, manager: ConfigMapManager, client: Client, charm: CharmBase) -> None:
        super().__init__("identity-schemas", manager, client, charm)


class ProvidersConfigMap(BaseConfigMap):
    """Class for managing the Providers configMap."""

    def __init__(self, manager: ConfigMapManager, client: Client, charm: CharmBase) -> None:
        super().__init__("providers", manager, client, charm)
