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


class ConfigMapHandler(CharmBase):
    """A helper object for managing the configMaps holding the kratos config."""

    kratos_config_map_name = "kratos-config"
    providers_config_map_name = "providers"
    identity_schemas_config_map_name = "identity-schemas"

    def __init__(self, client: Client, charm: CharmBase) -> None:
        self.client = client
        self.charm = charm

    def _create_map(self, configmap_name: str) -> None:
        try:
            self.client.get(ConfigMap, configmap_name, namespace=self.charm.model.name)
            return
        except ApiError:
            pass

        cm = ConfigMap(
            apiVersion="v1",
            kind="ConfigMap",
            # TODO @nsklikas: revisit labels
            metadata=ObjectMeta(
                name=configmap_name,
                labels={
                    "juju-app-name": self.charm.app.name,
                    "app.kubernetes.io/managed-by": "juju",
                },
            ),
        )
        self.client.create(cm)

    def _update_map(self, configmap_name: str, data: Dict) -> None:
        try:
            cm = self.client.get(ConfigMap, configmap_name, namespace=self.charm.model.name)
        except ApiError:
            return
        cm.data = data
        self.client.replace(cm)

    def _get_map(self, configmap_name: str) -> Dict:
        try:
            cm = self.client.get(ConfigMap, configmap_name, namespace=self.charm.model.name)
        except ApiError:
            return {}
        return cm.data

    def _delete_map(self, configmap_name: str) -> None:
        try:
            self.client.delete(ConfigMap, configmap_name, namespace=self.charm.model.name)
        except ApiError:
            raise ValueError

    def create_all_configmaps(self) -> None:
        """Create all the configMaps."""
        self.create_kratos_config()
        self.create_identity_schemas()
        self.create_providers()

    def delete_all_configmaps(self) -> None:
        """Delete all the configMaps."""
        self.delete_kratos_config()
        self.delete_identity_schemas()
        self.delete_providers()

    def create_providers(self) -> None:
        """Create the OIDC Providers configMap."""
        return self._create_map(self.providers_config_map_name)

    def update_providers(self, data: Dict[str, str]) -> None:
        """Update the OIDC Providers configMap."""
        return self._update_map(self.providers_config_map_name, data)

    def get_providers(self) -> Dict:
        """Get the OIDC Providers configMap."""
        return self._get_map(self.providers_config_map_name)

    def delete_providers(self) -> None:
        """Delete the OIDC Providers configMap."""
        return self._delete_map(self.providers_config_map_name)

    def create_identity_schemas(self) -> None:
        """Create the Identity Schemas configMap."""
        return self._create_map(self.identity_schemas_config_map_name)

    def update_identity_schemas(self, data: Dict[str, str]) -> None:
        """Update the Identity Schemas configMap."""
        return self._update_map(self.identity_schemas_config_map_name, data)

    def get_identity_schemas(self) -> Dict:
        """Get the Identity Schemas configMap."""
        return self._get_map(self.identity_schemas_config_map_name)

    def delete_identity_schemas(self) -> None:
        """Delete the Identity Schemas configMap."""
        return self._delete_map(self.identity_schemas_config_map_name)

    def create_kratos_config(self) -> None:
        """Create the Kratos Config configMap."""
        return self._create_map(self.kratos_config_map_name)

    def update_kratos_config(self, data: Dict[str, str]) -> None:
        """Update the Kratos Config configMap."""
        return self._update_map(self.kratos_config_map_name, data)

    def get_kratos_config(self) -> Dict:
        """Get the Kratos Config configMap."""
        return self._get_map(self.kratos_config_map_name)

    def delete_kratos_config(self) -> None:
        """Delete the Kratos Config configMap."""
        return self._delete_map(self.kratos_config_map_name)
