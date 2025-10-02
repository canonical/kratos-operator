#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for sharing Identity Platform Login UI application's endpoints with other charms.
This library provides a Python API for both requesting and providing a public endpoints.
## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.identity_platform_login_ui.v0.login_ui_endpoints
```
To use the library from the requirer side:
In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
  ui-endpoints-info:
    interface: login_ui_endpoints
    limit: 1
```
Then, to initialise the library:
```python
from charms.identity_platform_login_ui.v0.login_ui_endpoints import (
    LoginUIEndpointsRelationError,
    LoginUIEndpointsRequirer,
)
Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.login_ui_endpoints_relation = LoginUIEndpointsRequirer(self)
        self.framework.observe(self.on.some_event_emitted, self.some_event_function)
    def some_event_function():
        # fetch the relation info
        try:
            login_ui_endpoints = self.login_ui_endpoints_relation.get_login_ui_endpoints()
        except LoginUIEndpointsRelationError as error:
            ...
```
"""

from typing import List
import logging
from typing import Dict, Optional

from ops.charm import CharmBase, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents
from ops import Relation, ModelError
from pydantic import BaseModel

# The unique Charmhub library identifier, never change it
LIBID = "f59057701b5840849d3cea756af404c6"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 4

RELATION_NAME = "ui-endpoint-info"
INTERFACE_NAME = "login_ui_endpoints"
logger = logging.getLogger(__name__)


class LoginUIProviderData(BaseModel):
    consent_url: Optional[str] = None
    error_url: Optional[str] = None
    login_url: Optional[str] = None
    oidc_error_url: Optional[str] = None
    device_verification_url: Optional[str] = None
    post_device_done_url: Optional[str] = None
    recovery_url: Optional[str] = None
    registration_url: Optional[str] = None
    settings_url: Optional[str] = None
    webauthn_settings_url: Optional[str] = None
    account_linking_settings_url: Optional[str] = None


class LoginUIEndpointsRelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""


class LoginUIEndpointsProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `LoginUIEndpointsProvider`."""

    ready = EventSource(LoginUIEndpointsRelationReadyEvent)


class LoginUIEndpointsProvider(Object):
    """Provider side of the endpoint-info relation."""

    on = LoginUIEndpointsProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(
            events.relation_created, self._on_provider_endpoints_relation_created
        )

    def _on_provider_endpoints_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit()

    def send_endpoints_relation_data(self, data: LoginUIProviderData) -> None:
        """Updates relation with endpoint info."""
        if not self._charm.unit.is_leader():
            return None

        relations = self.model.relations[self._relation_name]

        for relation in relations:
            relation.data[self._charm.app].update(data.model_dump(exclude_none=True))


class LoginUIEndpointsRelationError(Exception):
    """Base class for the relation exceptions."""

    pass


class LoginUIEndpointsConflictError(LoginUIEndpointsRelationError):
    """Raised when we got the same uri multiple times."""

    def __init__(self) -> None:
        self.message = "Got the same uri from multiple relations"
        super().__init__(self.message)


class LoginUIEndpointsRequirer(Object):
    """Requirer side of the ui-endpoint-info relation."""

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)
        self.charm = charm
        self._relation_name = relation_name

    @property
    def relations(self) -> List[Relation]:
        """The list of Relation instances associated with this relation_name."""
        return [
            relation
            for relation in self.charm.model.relations[self._relation_name]
            if relation.active
        ]

    def _get_login_ui_endpoints_data(self, relation: Relation) -> Optional[Dict]:
        return relation.data[relation.app] if relation.app else None

    def get_login_ui_endpoints(self, relation_id=None) -> Optional[Dict]:
        """Get the Identity Platform Login UI endpoints."""
        if relation_id:
            relations = [self.model.get_relation(self._relation_name, relation_id=relation_id)]
        else:
            relations = self.relations

        if not relations:
            return None

        data = {}
        for r in relations:
            d = self._get_login_ui_endpoints_data(r)
            if not d:
                continue
            if set(d.keys()).intersection(data.keys()):
                raise LoginUIEndpointsConflictError()
            data.update(d)

        return data
