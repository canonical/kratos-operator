#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for providing for sharing application information between the Identity Platform Admin UI
charm and the Kratos, Hydra, and Oathkeeper charms.
This library provides a Python API for both requesting and providing endpoints and Kubernetes metadata, that is appropriate
for the relation between Admin UI and the specific Identity Platform Component.
## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.identity_platform_admin_ui.v0.admin_ui_service
```
To use the library with the Kratos charm:
In the `metadata.yaml` of the charm, add the following:
```yaml
provides:
  kratos-admin-endpoint:
    interface: admin_ui_service
```
Then, to initialise the library:
```python
from charms.identity_platform_admin_ui_operator.v0.admin_ui_service import (
    KratosAdminUIServiceProvider,
)
Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.admin_ui_provider = KratosAdminUIServiceProvider(self)
        self.framework.observe(
            self.admin_ui_provider.on.ready, self.some_event_function
        )
    def some_event_function():
        self.admin_ui_provider.send_relation_data_for_admin_ui(
            ...
        )
            ...
```
"""

import logging
from typing import Dict

from ops.charm import CharmBase, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents

# The unique Charmhub library identifier, never change it
LIBID = "temporary"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

INTERFACE_NAME = "admin_ui_service"
HYDRA_RELATION_NAME = "hydra-admin-endpoint"
KRATOS_RELATION_NAME = "kratos-admin-endpoint"
OAUTHKEEPER_RELATION_NAME = "oathkeeper-admin-endpoint"
logger = logging.getLogger(__name__)

# Generic Classes for relation. Please use appropriate subclass for the relation.


class AdminUIServiceRelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""


class AdminUIServiceProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `AdminUIServiceProvider`."""

    ready = EventSource(AdminUIServiceRelationReadyEvent)


class GenericAdminUIServiceProvider(Object):
    """Generic Provider of the admin_ui_service interface"""

    on = AdminUIServiceProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(
            events.relation_created, self._on_admin_ui_service_provider_ready
        )

    def _on_admin_ui_service_provider_ready(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit()

    def send_relation_data_for_admin_ui(self, relation_data: Dict) -> None:
        """Updates relation with data in relation_data parameter"""
        if not self._charm.unit.is_leader():
            return

        relations = self.model.relations[self._relation_name]
        for relation in relations:
            relation.data[self._charm.app].update(
                relation_data
            )


class AdminUIServiceRelationError(Exception):
    """Base class for relation exceptions."""

    pass


class AdminUIServiceRelationMissingError(AdminUIServiceRelationError):
    """Raised when the relation is missing."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class AdminUIServiceRelationDataMissingError(AdminUIServiceRelationError):
    """Raised when information is missing from relation data."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class GenericAdminUIServiceRequirer(Object):
    """Generic Requirer of the admin_ui_service interface"""

    def __init__(self, charm: CharmBase, relation_name: str) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

    def get_relation_data(self) -> Dict:
        """Receive relation data."""
        relation = self.model.relations[self._relation_name]
        if len(relation) == 0:
            raise AdminUIServiceRelationMissingError(
                f"Missing {self._relation_name} relation"
            )

        return relation[0].data[relation[0].app]


# Subclasses for relation with Kratos Charm


class KratosAdminUIServiceProvider(GenericAdminUIServiceProvider):
    """Helper provider subclass for relation with Kratos Provider"""

    def __init__(self, charm: CharmBase, relation_name: str = KRATOS_RELATION_NAME):
        super().__init__(charm, relation_name)

    def send_relation_data_for_admin_ui(self, admin_endpoint: str, public_endpoint: str, model_name: str, idp_configmap: str, schemas_configmap: str) -> None:
        """Updates relation with data specific to Kratos administration"""

        super().send_relation_data_for_admin_ui(
            {
                "admin_endpoint": admin_endpoint,
                "public_endpoint": public_endpoint,
                "model": model_name,
                "idp_configmap": idp_configmap,
                "schemas_configmap": schemas_configmap,
            }
        )


class KratosAdminUIServiceRequirer(GenericAdminUIServiceRequirer):
    """Helper requirer subclass for relation with Kratos Provider"""

    def __init__(self, charm: CharmBase, relation_name: str = KRATOS_RELATION_NAME) -> None:
        super().__init__(charm, relation_name)

    def get_relation_data(self) -> Dict:
        data = super().get_relation_data()

        for field in [
            "admin_endpoint",
            "public_endpoint",
            "model",
            "idp_configmap",
            "schemas_configmap"
        ]:
            if field not in data:
                raise AdminUIServiceRelationDataMissingError(f"Missing {field} field in relation data")

        return {
            "admin_endpoint": data["admin_endpoint"],
            "public_endpoint": data["public_endpoint"],
            "model": data["model"],
            "idp_configmap": data["idp_configmap"],
            "schemas_configmap": data["schemas_configmap"],
        }


# Subclasses for relation with Hydra Charm


class HydraAdminUIServiceProvider(GenericAdminUIServiceProvider):
    """Helper provider subclass for relation with Hydra Provider"""

    def __init__(self, charm: CharmBase, relation_name: str = HYDRA_RELATION_NAME):
        super().__init__(charm, relation_name)

    def send_relation_data_for_admin_ui(self, admin_endpoint: str) -> None:
        """Updates relation with data specific to Hydra administration"""

        super().send_relation_data_for_admin_ui(
            {
                "admin_endpoint": admin_endpoint,
            }
        )


class HydraAdminUIServiceRequirer(GenericAdminUIServiceRequirer):
    """Helper requirer subclass for relation with Hydra Provider"""

    def __init__(self, charm: CharmBase, relation_name: str = HYDRA_RELATION_NAME) -> None:
        super().__init__(charm, relation_name)

    def get_relation_data(self) -> Dict:
        data = super().get_relation_data()

        if "admin_endpoint" not in data:
            raise AdminUIServiceRelationDataMissingError("Missing admin_endpoint field in relation data")

        return {
            "admin_endpoint": data["admin_endpoint"]
        }


# Subclasses for relation with Oathkeeper Charm


class OathkeeperAdminUIServiceProvider(GenericAdminUIServiceProvider):
    """Helper provider subclass for relation with Oathkeeper Provider"""

    def __init__(self, charm: CharmBase, relation_name: str = OAUTHKEEPER_RELATION_NAME):
        super().__init__(charm, relation_name)

    def send_relation_data_for_admin_ui(self, public_endpoint: str, rules_configmap: str, rules_file: str, model: str) -> None:
        """Updates relation with data specific to Oathkeeper administration"""

        super().send_relation_data_for_admin_ui(
            {
                "public_endpoint": public_endpoint,
                "rules_configmap": rules_configmap,
                "rules_file": rules_file,
                "model": model,
            }
        )


class OathkeeperAdminUIServiceRequirer(GenericAdminUIServiceRequirer):
    """Helper class for relation with Oathkeeper Provider"""

    def __init__(self, charm: CharmBase, relation_name: str = OAUTHKEEPER_RELATION_NAME) -> None:
        super().__init__(charm, relation_name)

    def get_relation_data(self) -> Dict:
        data = super().get_relation_data()

        for field in [
            "public_endpoint",
            "model",
            "rules_configmap",
            "rules_file"
        ]:
            if field not in data:
                raise AdminUIServiceRelationDataMissingError(f"Missing {field} field in relation data")

        return {
            "public_endpoint": data["public_endpoint"],
            "rules_configmap": data["rules_configmap"],
            "rules_file": data["rules_file"],
            "model": data["model"],
        }
