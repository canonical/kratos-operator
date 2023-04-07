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

import logging
from typing import Dict, Optional

from ops.charm import CharmBase, RelationCreatedEvent
from ops.framework import EventBase, EventSource, Object, ObjectEvents

# The unique Charmhub library identifier, never change it
LIBID = "460ab09e6b874d1c891b67f83586c9a7"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

RELATION_NAME = "ui-endpoint-info"
INTERFACE_NAME = "login_ui_endpoints"
logger = logging.getLogger(__name__)

RELATION_KEYS = [
    "consent_url",
    "error_url",
    "index_url",
    "login_url",
    "oidc_error_url",
    "registration_url",
    "default_url",
]


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

    def send_endpoints_relation_data(self, endpoint: str) -> None:
        """Updates relation with endpoint info."""
        if not self._charm.unit.is_leader():
            return

        relations = self.model.relations[self._relation_name]
        for relation in relations:
            relation.data[self._charm.app].update(
                {
                    "consent_url": f"{endpoint}/consent",
                    "error_url": f"{endpoint}/error",
                    "index_url": f"{endpoint}/index",
                    "login_url": f"{endpoint}/login",
                    "oidc_error_url": f"{endpoint}/oidc_error",
                    "registration_url": f"{endpoint}/registration",
                    "default_url": endpoint,
                }
            )


class LoginUIEndpointsRelationError(Exception):
    """Base class for the relation exceptions."""

    pass


class LoginUIEndpointsRelationMissingError(LoginUIEndpointsRelationError):
    """Raised when the relation is missing."""

    def __init__(self) -> None:
        self.message = "Missing ui-endpoint-info relation with Identity Platform Login UI"
        super().__init__(self.message)


class LoginUIEndpointsRelationDataMissingError(LoginUIEndpointsRelationError):
    """Raised when information is missing from the relation."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class LoginUIEndpointsRelationUnavailableError(LoginUIEndpointsRelationError):
    """Raised when Login UI cannot be accessed."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(self.message)


class LoginUIEndpointsRequirer(Object):
    """Requirer side of the ui-endpoint-info relation."""

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)
        self.charm = charm
        self._relation_name = relation_name

    def get_login_ui_endpoints(self) -> Optional[Dict]:
        """Get the Identity Platform Login UI endpoints."""
        if not self.model.unit.is_leader():
            return None
        endpoints = self.model.relations[self._relation_name]
        if len(endpoints) == 0:
            raise LoginUIEndpointsRelationMissingError()

        data = endpoints[0].data[endpoints[0].app]
                
        if any(not data.get(k := key) for key in RELATION_KEYS):
            raise LoginUIEndpointsRelationDataMissingError(
                f"Missing endpoint {k} in ui-endpoint-info relation data"
            )

        if data["default_url"] == "":
            raise LoginUIEndpointsRelationUnavailableError(
                "Endpoints in ui-endpoint-info are unavailable"
            )

        return dict(data)
