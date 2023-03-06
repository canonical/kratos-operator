#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for sharing hydra endpoints.

This library provides a Python API for both requesting and providing public and admin endpoints.

## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.hydra.v0.hydra_endpoints
```

To use the library from the requirer side:
In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
  endpoint-info:
    interface: hydra_endpoints
    limit: 1
```
Then, to initialise the library:
```python
from charms.hydra.v0.hydra_endpoints import (
    HydraEndpointsRelationError,
    HydraEndpointsRequirer,
)

Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.hydra_endpoints_relation = HydraEndpointsRequirer(self)
        self.framework.observe(self.on.some_event_emitted, self.some_event_function)
    def some_event_function():
        # fetch the relation info
        try:
            hydra_data = self.hydra_endpoints_relation.get_hydra_endpoints()
        except HydraEndpointsRelationError as error:
            ...
```

"""

import logging

from ops.charm import (
    CharmBase,
    RelationCreatedEvent,
)
from ops.framework import EventBase, EventSource, Object, ObjectEvents
from ops.model import Application

# The unique Charmhub library identifier, never change it
LIBID = "a9dbc14576874a508dc3b7f717c72f73"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

RELATION_NAME = "endpoint-info"
INTERFACE_NAME = "hydra_endpoints"
logger = logging.getLogger(__name__)


class HydraEndpointsRelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""


class HydraEndpointsProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `HydraEndpointsProvider`."""

    ready = EventSource(HydraEndpointsRelationReadyEvent)


class HydraEndpointsProvider(Object):
    """Provider side of the endpoint-info relation."""

    on = HydraEndpointsProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_provider_endpoint_relation_created)

    def _on_provider_endpoint_relation_created(self, event: RelationCreatedEvent):
        self.on.ready.emit()

    def send_endpoint_relation_data(
        self, charm: CharmBase, admin_endpoint: str, public_endpoint: str
    ) -> None:
        """Updates relation with endpoints info."""
        if not self._charm.unit.is_leader():
            return

        relations = self.model.relations[RELATION_NAME]
        for relation in relations:
            relation.data[charm].update(
                {
                    "admin_endpoint": admin_endpoint,
                    "public_endpoint": public_endpoint,
                }
            )


class HydraEndpointsRelationError(Exception):
    pass


class HydraEndpointsRelationMissingError(HydraEndpointsRelationError):
    def __init__(self):
        self.message = "Missing endpoint-info relation with hydra"
        super().__init__(self.message)


class HydraEndpointsRelationDataMissingError(HydraEndpointsRelationError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class HydraEndpointsRequirer(Object):
    """Requirer side of the endpoint-info relation."""

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name

    def get_hydra_endpoints(self) -> dict:
        if not self.model.unit.is_leader():
            return
        endpoints = self.model.relations[self.relation_name]
        if len(endpoints) == 0:
            raise HydraEndpointsRelationMissingError()

        remote_app = [
            app
            for app in endpoints[0].data.keys()
            if isinstance(app, Application) and not app._is_our_app
        ][0]

        data = endpoints[0].data[remote_app]

        if not "admin_endpoint" in data:
            raise HydraEndpointsRelationDataMissingError(
                "Missing admin endpoint in endpoint-info relation data"
            )

        return {
            "admin_endpoint": data["admin_endpoint"],
            "public_endpoint": data["public_endpoint"],
        }
