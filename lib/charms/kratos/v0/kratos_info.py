#!/usr/bin/env python3
# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for sharing kratos info.

This library provides a Python API for both requesting and providing kratos deployment info,
such as endpoints, namespace and ConfigMap details.
## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.kratos.v0.kratos_info
```
To use the library from the requirer side:
In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
  kratos-info:
    interface: kratos_info
    limit: 1
```
Then, to initialise the library:
```python
from charms.kratos.v0.kratos_info import (
    KratosInfoRelationError,
    KratosInfoRequirer,
)
Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.kratos_info_relation = KratosInfoRequirer(self)
        self.framework.observe(self.on.some_event_emitted, self.some_event_function)
    def some_event_function():
        # fetch the relation info
        try:
            kratos_data = self.kratos_info_relation.get_kratos_info()
        except KratosInfoRelationError as error:
            ...
```
"""

import logging
from os.path import join
from typing import Dict, Optional

from ops.charm import CharmBase, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents

# The unique Charmhub library identifier, never change it
LIBID = "40d36890fe6d40409ccee34aa9245d4a"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 4

RELATION_NAME = "kratos-info"
INTERFACE_NAME = "kratos_info"
logger = logging.getLogger(__name__)


class KratosInfoRelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""


class KratosInfoProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `KratosInfoProvider`."""

    ready = EventSource(KratosInfoRelationReadyEvent)


class KratosInfoProvider(Object):
    """Provider side of the kratos-info relation."""

    on = KratosInfoProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_info_provider_relation_created)

    def _on_info_provider_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit()

    def send_info_relation_data(
        self,
        admin_endpoint: str,
        public_endpoint: str,
        external_url: str,
        providers_configmap_name: str,
        schemas_configmap_name: str,
        configmaps_namespace: str,
        mfa_enabled: bool,
        oidc_webauthn_sequencing_enabled: bool,
    ) -> None:
        """Updates relation with endpoints, config and configmaps info."""
        if not self._charm.unit.is_leader():
            return

        external_url = external_url if external_url.endswith("/") else external_url + "/"

        relations = self.model.relations[self._relation_name]
        info_databag = {
            "admin_endpoint": admin_endpoint,
            "public_endpoint": public_endpoint,
            "login_browser_endpoint": join(external_url, "self-service/login/browser"),
            "sessions_endpoint": f"{public_endpoint}/sessions/whoami",
            "providers_configmap_name": providers_configmap_name,
            "schemas_configmap_name": schemas_configmap_name,
            "configmaps_namespace": configmaps_namespace,
            "mfa_enabled": str(mfa_enabled),
            "oidc_webauthn_sequencing_enabled": str(oidc_webauthn_sequencing_enabled),
        }

        for relation in relations:
            relation.data[self._charm.app].update(info_databag)


class KratosInfoRelationError(Exception):
    """Base class for the relation exceptions."""

    pass


class KratosInfoRelationMissingError(KratosInfoRelationError):
    """Raised when the relation is missing."""

    def __init__(self) -> None:
        self.message = "Missing kratos-info relation with kratos"
        super().__init__(self.message)


class KratosInfoRelationDataMissingError(KratosInfoRelationError):
    """Raised when information is missing from the relation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class KratosInfoRequirer(Object):
    """Requirer side of the kratos-info relation."""

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name

    def is_ready(self) -> bool:
        relation = self.model.get_relation(self.relation_name)
        if not relation or not relation.app or not relation.data[relation.app]:
            return False
        return True

    def get_kratos_info(self) -> Optional[Dict]:
        """Get the kratos info."""
        info = self.model.relations[self.relation_name]
        if len(info) == 0:
            raise KratosInfoRelationMissingError()

        if not (app := info[0].app):
            raise KratosInfoRelationMissingError()

        data = info[0].data[app]

        if not data:
            logger.info("No relation data available.")
            raise KratosInfoRelationDataMissingError("Missing relation data")

        return data
