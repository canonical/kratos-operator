#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for configuring a kratos registration webhook.

The provider side is responsible for providing the configuration that kratos
will use to call this webhook.

The requirer side (kratos) takes the configuration provided and updates its
config.
"""

import logging
from functools import cached_property
from string import Template
from typing import Annotated, List, Optional

from ops import (
    CharmBase,
    EventSource,
    ModelError,
    Object,
    ObjectEvents,
    Relation,
    RelationBrokenEvent,
    RelationCreatedEvent,
    RelationEvent,
    Secret,
    SecretNotFoundError,
)
from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    PlainSerializer,
    StrictBool,
    field_serializer,
)

LIBID = "37ddb4471fae41adb74299f091ee3a28"
LIBAPI = 0
LIBPATCH = 5

PYDEPS = ["pydantic"]

RELATION_NAME = "kratos-registration-webhook"
INTERFACE_NAME = "kratos_registration_webhook"

API_KEY_SECRET_LABEL_TEMPLATE = Template("relation-$relation_id-api-key-secret")

logger = logging.getLogger(__name__)


def deserialize_bool(v: str | bool) -> bool:
    if isinstance(v, str):
        return True if v.casefold() == "true" else False

    return v


SerializableBool = Annotated[
    StrictBool,
    PlainSerializer(lambda v: str(v), return_type=str),
    BeforeValidator(deserialize_bool),
]


class ProviderData(BaseModel):
    url: str
    body: str
    method: str
    emit_analytics_event: SerializableBool = False
    response_ignore: SerializableBool
    response_parse: SerializableBool
    auth_type: str = Field(default="api_key")
    auth_config_name: Optional[str] = Field(default="Authorization")
    auth_config_value: Optional[str] = Field(default=None, exclude=True)
    auth_config_value_secret: Optional[str] = None
    auth_config_in: Optional[str] = Field(default="header")

    @cached_property
    def auth_enabled(self) -> bool:
        return all(
            [
                self.auth_type,
                self.auth_config_name,
                self.auth_config_value_secret or self.auth_config_value,
                self.auth_config_in,
            ]
        )

    @field_serializer(
        "auth_type",
        "auth_config_name",
        "auth_config_value",
        "auth_config_value_secret",
        "auth_config_in",
    )
    def auth_serializer(self, v: Optional[str]) -> str:
        if self.auth_enabled:
            return v
        return ""


class ReadyEvent(RelationEvent):
    """An event when the integration is ready."""


class UnavailableEvent(RelationEvent):
    """An event when the integration is unavailable."""


class RelationEvents(ObjectEvents):
    ready = EventSource(ReadyEvent)
    unavailable = EventSource(UnavailableEvent)


class KratosRegistrationWebhookProvider(Object):
    """Provider side of the kratos-registration-webhook relation."""

    on = RelationEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_created, self._on_relation_created)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    def _on_relation_created(self, event: RelationCreatedEvent) -> None:
        self.on.ready.emit(event.relation)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the event emitted when the integration is broken."""
        self._delete_juju_secret(event.relation)
        self.on.unavailable.emit(event.relation)

    def update_relations_app_data(
        self,
        data: ProviderData,
    ) -> None:
        """Update the integration data."""
        if not self._charm.unit.is_leader():
            return None

        if not (relations := self._charm.model.relations.get(self._relation_name)):
            return

        for relation in relations:
            if data.auth_config_value:
                secret = self._create_or_update_secret(data.auth_config_value, relation)
                data.auth_config_value_secret = secret.id
            relation.data[self._charm.app].update(data.model_dump(exclude_none=True))

    def _delete_juju_secret(self, relation: Relation) -> None:
        try:
            secret = self.model.get_secret(
                label=API_KEY_SECRET_LABEL_TEMPLATE.substitute(relation_id=relation.id)
            )
        except SecretNotFoundError:
            return
        else:
            secret.remove_all_revisions()

    def _create_or_update_secret(self, auth_config_value: str, relation: Relation) -> Secret:
        """Create a juju secret and grant it to a relation."""
        label = API_KEY_SECRET_LABEL_TEMPLATE.substitute(relation_id=relation.id)
        content = {"auth-config-value": auth_config_value}
        try:
            secret = self._charm.model.get_secret(label=label)
            secret.set_content(content=content)
        except SecretNotFoundError:
            secret = self._charm.app.add_secret(label=label, content=content)
        secret.grant(relation)
        return secret


class KratosRegistrationWebhookRequirer(Object):
    """Requirer side of the kratos-registration-webhook relation."""

    on = RelationEvents()

    def __init__(self, charm: CharmBase, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)

        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_changed, self._on_relation_changed)
        self.framework.observe(events.relation_broken, self._on_relation_broken)

    def _on_relation_changed(self, event: RelationCreatedEvent) -> None:
        provider_app = event.relation.app

        if not event.relation.data.get(provider_app):
            return

        self.on.ready.emit(event.relation)

    def _on_relation_broken(self, event: RelationBrokenEvent) -> None:
        """Handle the event emitted when the integration is broken."""
        self.on.unavailable.emit(event.relation)

    def consume_relation_data(
        self,
        /,
        relation: Optional[Relation] = None,
        relation_id: Optional[int] = None,
    ) -> Optional[ProviderData]:
        """An API for the requirer charm to consume the related information in the application databag."""
        if not relation:
            relation = self._charm.model.get_relation(self._relation_name, relation_id)

        if not relation:
            return None

        provider_data = dict(relation.data.get(relation.app))
        if secret_id := provider_data.get("auth_config_value_secret"):
            secret = self._charm.model.get_secret(id=secret_id)
            provider_data["auth_config_value"] = secret.get_content().get("auth-config-value")
        return ProviderData(**provider_data) if provider_data else None

    def _is_relation_active(self, relation: Relation) -> bool:
        """Whether the relation is active based on contained data."""
        try:
            _ = repr(relation.data)
            return True
        except (RuntimeError, ModelError):
            return False

    @property
    def relations(self) -> List[Relation]:
        """The list of Relation instances associated with this relation_name."""
        return [
            relation
            for relation in self._charm.model.relations[self._relation_name]
            if self._is_relation_active(relation)
        ]

    def _ready(self, relation: Relation) -> bool:
        if not relation.app:
            return False

        return "url" in relation.data[relation.app] and "body" in relation.data[relation.app]

    def ready(self, relation_id: Optional[int] = None) -> bool:
        """Check if the relation data is ready."""
        if relation_id is None:
            return (
                all(self._ready(relation) for relation in self.relations)
                if self.relations
                else False
            )

        try:
            relation = [relation for relation in self.relations if relation.id == relation_id][0]
            return self._ready(relation)
        except IndexError:
            raise IndexError(f"relation id {relation_id} cannot be accessed")
