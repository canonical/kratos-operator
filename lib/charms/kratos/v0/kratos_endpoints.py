#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for sharing kratos endpoints.
This library provides a Python API for both requesting and providing public and admin endpoints.
## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.kratos.v0.kratos_endpoints
```
To use the library from the requirer side:
In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
  kratos-endpoint-info:
    interface: kratos_endpoints
    limit: 1
```
Then, to initialise the library:
```python
from charms.kratos.v0.kratos_endpoints import (
    KratosEndpointsRelationError,
    KratosEndpointsRequirer,
)
Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.kratos_endpoints_relation = KratosEndpointsRequirer(self)
        self.framework.observe(self.on.some_event_emitted, self.some_event_function)
    def some_event_function():
        # fetch the relation info
        try:
            kratos_data = self.kratos_endpoints_relation.get_kratos_endpoints()
        except KratosEndpointsRelationError as error:
            ...
```
"""

import logging
from typing import Dict, Optional

from ops.charm import CharmBase, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents
from ops.model import Application

# The unique Charmhub library identifier, never change it
LIBID = "5868b36df1c04c90b33f5e5557327162"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

RELATION_NAME = "kratos-endpoint-info"
INTERFACE_NAME = "kratos_endpoints"
logger = logging.getLogger(__name__)


class KratosEndpointsRelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""


class KratosEndpointsProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `KratosEndpointsProvider`."""

    ready = EventSource(KratosEndpointsRelationReadyEvent)


class KratosEndpointsProvider(Object):
    """Provider side of the kratos-endpoint-info relation."""

    on = KratosEndpointsProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(
            events.relation_created, self._on_provider_endpoint_relation_created
        )

    def _on_provider_endpoint_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit()

    def send_endpoint_relation_data(self, admin_endpoint: str, public_endpoint: str) -> None:
        """Updates relation with endpoints info."""
        if not self._charm.unit.is_leader():
            return

        relations = self.model.relations[self._relation_name]
        for relation in relations:
            relation.data[self._charm.app].update(
                {
                    "admin_endpoint": admin_endpoint,
                    "public_endpoint": public_endpoint,
                }
            )


class KratosEndpointsRelationError(Exception):
    """Base class for the relation exceptions."""

    pass


class KratosEndpointsRelationMissingError(KratosEndpointsRelationError):
    """Raised when the relation is missing."""

    def __init__(self) -> None:
        self.message = "Missing kratos-endpoint-info relation with kratos"
        super().__init__(self.message)


class KratosEndpointsRelationDataMissingError(KratosEndpointsRelationError):
    """Raised when information is missing from the relation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class KratosEndpointsRequirer(Object):
    """Requirer side of the kratos-endpoint-info relation."""

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name

    def get_kratos_endpoints(self) -> Optional[Dict]:
        """Get the kratos endpoints."""
        endpoints = self.model.relations[self.relation_name]
        if len(endpoints) == 0:
            raise KratosEndpointsRelationMissingError()

        data = endpoints[0].data[endpoints[0].app]

        if "public_endpoint" not in data:
            raise KratosEndpointsRelationDataMissingError(
                "Missing public endpoint in kratos-endpoint-info relation data"
            )

        return {
            "admin_endpoint": data["admin_endpoint"],
            "public_endpoint": data["public_endpoint"],
        }
