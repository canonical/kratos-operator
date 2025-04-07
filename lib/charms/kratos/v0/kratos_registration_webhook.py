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
from typing import Annotated, Any, List, Optional, TypeVar, Union

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
)
from pydantic import BaseModel as _BaseModel
from pydantic import (
    BeforeValidator,
    Field,
    FieldValidationInfo,
    PlainSerializer,
    StrictBool,
)
from pydantic_core import from_json

LIBID = "37ddb4471fae41adb74299f091ee3a28"
LIBAPI = 0
LIBPATCH = 2

PYDEPS = ["pydantic"]

RELATION_NAME = "kratos-registration-webhook"
INTERFACE_NAME = "kratos_registration_webhook"
logger = logging.getLogger(__name__)


class BaseModel(_BaseModel):
    def __init__(self, **data: Any) -> None:
        # We override the init function to add a reference to self in the context
        # so that "deserialize_model" can use it.
        self.__pydantic_validator__.validate_python(
            data,
            self_instance=self,
            context={"self": self},
        )


def deserialize_bool(v: str | bool) -> bool:
    if isinstance(v, str):
        return True if v.casefold() == "true" else False

    return v


def deserialize_model(v: BaseModel | str, info: FieldValidationInfo) -> BaseModel:
    if isinstance(v, BaseModel):
        return v

    return info.context["self"].model_fields[info.field_name].annotation(**from_json(v))


SerializableBool = Annotated[
    StrictBool,
    PlainSerializer(lambda v: str(v), return_type=str),
    BeforeValidator(deserialize_bool),
]


SerializableModel = Annotated[
    TypeVar("BaseModelType", bound=BaseModel),
    PlainSerializer(lambda v: v.model_dump_json(exclude_none=True), return_type=str),
    BeforeValidator(deserialize_model),
]


class ResponseConfig(BaseModel):
    ignore: SerializableBool
    parse: SerializableBool


class _AuthConfig(BaseModel):
    name: Optional[str] = "Authorization"
    value: str
    in_: Optional[str] = Field(default="header", alias="in")


class AuthConfig(BaseModel):
    type: Optional[str] = Field("api_key")
    config: _AuthConfig


class ProviderData(BaseModel):
    url: str
    body: str
    method: str
    emit_analytics_event: SerializableBool
    response: SerializableModel[ResponseConfig]
    auth: Optional[AuthConfig] = None


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
        self.on.unavailable.emit(event.relation)

    def update_relations_app_data(
        self,
        data: Union[ProviderData],
    ) -> None:
        """Update the integration data."""
        if not (relations := self._charm.model.relations.get(self._relation_name)):
            return

        for relation in relations:
            relation.data[self._charm.app].update(data.model_dump(exclude_none=True))


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
