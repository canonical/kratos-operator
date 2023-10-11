#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Library to manage the relation between the Kratos operator and the Oathkeeper operator.

In the context of the Canonical Identity Platform, the Oathkeeper uses Kratos to authenticate 
incoming requests. This library contains the Requires and Provides classes that allow the Oathkeeper
operator to discover the Kratos operator. This library also contains custem events that
provide a convenience when implementing the data transfer between Oathkeeper and Kratos.

"""
import datetime
import logging
import json
from typing import List, Optional, Tuple

from ops.charm import (
    CharmBase,
    CharmEvents,
    RelationChangedEvent,
    RelationCreatedEvent,
)
from ops.framework import EventSource, EventBase, Object, ObjectEvents


# The unique Charmhub library identifier, never change it
LIBID = "temporary"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

PYDEPS = ["ops>=2.0.0"]

logger = logging.getLogger(__name__)

RELATION_NAME = "session_authentication"
INTERFACE_NAME = "session_auth"

# General Events


class AuthSessionsReadyEvent(EventBase):
    """This event will be created when the relation is ready"""

# Events for SessionAuthProvider.


class AllowedURLsChangedEvent(EventBase):
    """This event will be created when there's a change in the allowed urls"""


class SessionAuthProviderEvents(CharmEvents):
    allowed_urls_updated = EventSource(AllowedURLsChangedEvent)
    ready = EventSource(AuthSessionsReadyEvent)


# Events for SessionAuthRequirer


class AuthSessionEndpointUpdatedEvent(EventBase):
    """This event will be created when one or more relevant Kratos endpoints are updated"""


class SessionAuthRequirerEvents(CharmEvents):
    endpoints_updated = EventSource(AuthSessionEndpointUpdatedEvent)
    ready = EventSource(AuthSessionsReadyEvent)


# Exceptions


class SessionAuthRelationError(Exception):
    """Base exception"""

    pass


class SessionAuthRelationMissingError(SessionAuthRelationError):
    """Raised when the relation is missing."""

    def __init__(self) -> None:
        self.message = "Missing session-authentication relation"
        super().__init__(self.message)

# SessionAuthProvider is to be implemented by the Kratos Operator.


class SessionAuthProvider(Object):
    """Provider class to facilitate Kratos' side of the relation"""

    on = SessionAuthProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        events = self._charm.on[relation_name]
        self.framework.observe(
            events.relation_created, self._on_session_auth_relation_created
        )

    def _on_session_auth_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit()

    def _on_relation_changed(self, event: RelationChangedEvent) -> None:
        """Event emitted when the relation has been changed."""

        # Emit a allowed_urls_updated event if the allowed urls have been updated
        logger.info("Allowed URLs updated at %s", datetime.now())
        self.on.allowed_urls_updated.emit()

    def set_endpoints(self, endpoint: str) -> None:
        """Sets the login browser and sessions endpoints for Oathkeeper to consume.

        This function writes in the application data bag, therefore,
        only the leader unit can call it.
        """
        if not self._charm.unit.is_leader():
            return

        relations = self.model.relations[self._relation_name]
        databag = {
                "sessions_endpoint": f"{endpoint}/sessions/whoami",
                "login_browser_endpoint": f"{endpoint}/self-service/login/browser",
        }
        for relation in relations:
            relation.data[self._charm.app].update(databag)

    def get_allowed_return_urls(self) -> List[str]:
        """Get the allowed return urls."""

        relations = self.model.relations[self._relation_name]
        if len(relations) == 0:
            logger.info("No session_auth relation found.")
            return []

        if not (app := relations[0].app):
            logger.info("No session_auth relation found.")
            return []

        databag = relations[0].data[app]

        if not databag:
            logger.info("No relation data available.")
            return []

        if "allowed_return_urls" not in databag:
            logger.info("No allowed return urls sent.")
            return []

        return json.loads(databag["allowed_return_urls"])

# SessionAuthRequirer is to be implemented by the Oathkeeper Operator.


class SessionAuthRequirer(Object):
    """Requirer class to facilitate the Oathkeeper' side of the relation"""

    on = SessionAuthRequirerEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name
        events = self._charm.on[relation_name]
        self.framework.observe(
            events.relation_created, self._on_session_auth_relation_created
        )

    def _on_session_auth_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit()

    def _on_relation_changed_event(self, event: RelationChangedEvent) -> None:
        """Event emitted when the relation has been changed."""

        self.on.endpoints_updated.emit()

    def set_allowed_return_urls(self, allowed_return_urls: List[str]) -> None:
        """Sets the allowed urls for Kratos to consume.

        This function writes in the application data bag, therefore,
        only the leader unit can call it.
        """
        if not self._charm.unit.is_leader():
            return

        urls = json.dumps(allowed_return_urls)
        relations = self.model.relations[self._relation_name]
        databag = {
                "allowed_return_urls": urls,
        }
        for relation in relations:
            relation.data[self._charm.app].update(databag)

    def get_session_auth_endpoints(self) -> Optional[Tuple[str, str]]:
        """get the login browser endpoint and the session endpoint"""

        relations = self.model.relations[self._relation_name]
        if len(relations) == 0:
            raise SessionAuthRelationMissingError()

        if not (app := relations[0].app):
            raise SessionAuthRelationMissingError()

        databag = relations[0].data[app]

        login = ""
        session = ""

        if not databag:
            logger.info("No relation data available.")
            return

        if "login_browser_endpoint" not in databag:
            logger.info("No login_browser_endpoint sent.")
        else:
            login = databag["login_browser_endpoint"]

        if "sessions_endpoint" not in databag:
            logger.info("No sessions_endpoint sent.")
        else:
            session = databag["sessions_endpoint"]

        return (login, session)
