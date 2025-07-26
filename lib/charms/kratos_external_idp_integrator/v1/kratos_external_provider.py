#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Interface library for Kratos external OIDC providers.

This library wraps relation endpoints using the `kratos-external-idp` interface
and provides a Python API for both requesting Kratos to register the client credentials
and for communicating with an external provider.

## Getting Started

To get started using the library, you need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.kratos_external_idp_integrator.v1.kratos_external_provider
```

To use the library from the provider side (KratosExternalIdpIntegrator):

In the `metadata.yaml` of the charm, add the following:
```yaml
provides:
    kratos-external-idp:
        interface: external_provider
        limit: 1
```

Then, to initialize the library:

```python
from charms.kratos_external_idp_integrator.v1.kratos_external_provider import (
    ExternalIdpProvider,
)
from ops.model import BlockedStatus

class SomeCharm(CharmBase):
  def __init__(self, *args):
    # ...
    self.external_idp_provider = ExternalIdpProvider(self, self.config)

    self.framework.observe(self.on.config_changed, self._on_config_changed)
    self.framework.observe(self.external_idp_provider.on.ready, self._on_ready)
    self.framework.observe(
        self.external_idp_provider.on.redirect_uri_changed, self._on_redirect_uri_changed
    )

    def _on_config_changed(self, event):
        # ...
        providers = self.external_idp_provider.validate_provider_config([self.config])
        if not providers:
            self.unit.status = BlockedStatus("Invalid configuration")
        # ...

    def _on_redirect_uri_changed(self, event):
        logger.info(f"The client's redirect_uri changed to {event.redirect_uri}")

    def _on_ready(self, event):
        if not isinstance(self.unit.status, BlockedStatus):
            self.external_idp_provider.create_providers(providers)
```

To use the library from the requirer side (Kratos):

In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
    kratos-external-idp:
        interface: external_provider
```

Then, to initialize the library:

```python
from charms.kratos_external_idp_integrator.v1.kratos_external_provider import (
    ExternalIdpRequirer
)

class KratosCharm(CharmBase):
  def __init__(self, *args):
    # ...
    self.external_idp_requirer = ExternalIdpRequirer(self)

    self.framework.observe(
        self.external_idp_provider.on.client_config_changed, self._on_client_config_changed
    )

    def _on_client_config_changed(self, event):
        self._configure(event)

        self.external_provider.update_registered_provider(
            providers,
            event.relation_id,
        )
```
"""

import base64
import hashlib
import json
import logging
from typing import Annotated, Iterator, Literal, Mapping, Optional, Union

from ops.charm import (
    CharmBase,
    RelationBrokenEvent,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationEvent,
    RelationJoinedEvent,
)
from ops.framework import EventBase, EventSource, Handle, Object, ObjectEvents
from ops.model import Relation, TooManyRelatedAppsError
from pydantic import (
    AliasChoices,
    BaseModel,
    Field,
    RootModel,
    SecretStr,
    SerializerFunctionWrapHandler,
    ValidationError,
    WrapSerializer,
    field_serializer,
    field_validator,
    model_validator,
)
from typing_extensions import Self

# The unique CharmHub library identifier, never change it
LIBID = "33040051de7f43a8bb43349f2b037dfc"

# Increment this major API version when introducing breaking changes
LIBAPI = 1

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 0

PYDEPS = ["pydantic~=2.11"]

logger = logging.getLogger(__name__)

DEFAULT_RELATION_NAME = "kratos-external-idp"
ALLOWED_PROVIDERS = {
    "generic",
    "google",
    "facebook",
    "microsoft",
    "github",
    "apple",
    "gitlab",
    "auth0",
    "slack",
    "spotify",
    "discord",
    "twitch",
    "netid",
    "yander",
    "vk",
    "dingtalk",
}


def dump_secret(v: SecretStr, _: SerializerFunctionWrapHandler) -> str:
    return v.get_secret_value()


Secret = Annotated[SecretStr, WrapSerializer(dump_secret)]


class BaseProvider(BaseModel):
    provider: str
    client_id: str
    scope: list[str] = ["profile", "email", "address", "phone"]
    id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("id", "provider_id"),
        serialization_alias="id",
    )
    label: Optional[str] = Field(default=None)
    jsonnet_mapper: Optional[str] = Field(default=None)
    mapper_url: Optional[str] = Field(default=None)
    relation_id: Optional[int] = Field(default=None, exclude=True)

    @field_validator("provider", mode="after")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in ALLOWED_PROVIDERS:
            raise ValueError(f"Unsupported external provider: {v}")

        return v

    @field_serializer("scope", when_used="json")
    def serialize_scope(self, v: list[str]) -> str:
        return " ".join(v)

    @field_validator("scope", mode="before")
    @classmethod
    def deserialize_scope(cls, v: Optional[str]) -> list[str]:
        v = v or "profile email address phone"
        return v.split()

    @model_validator(mode="after")
    def deserialize_mapper_url(self) -> Self:
        if self.mapper_url is None and self.jsonnet_mapper is not None:
            self.mapper_url = f"base64://{base64.b64encode(self.jsonnet_mapper.encode()).decode()}"

        return self

    @model_validator(mode="after")
    def deserialize_id(self) -> Self:
        if not self.id:
            identifier = hashlib.sha1(self.client_id.encode()).hexdigest()
            self.id = f"{self.provider}_{identifier}"

        return self

    @model_validator(mode="after")
    def deserialize_label(self) -> Self:
        self.label = self.label or self.provider
        return self


class GenericProvider(BaseProvider):
    provider: Literal["generic", "auth0"]
    issuer_url: str
    client_secret: Secret

    @model_validator(mode="after")
    def deserialize_id(self) -> Self:
        if not self.id:
            identifier = hashlib.sha1(f"{self.client_id}_{self.issuer_url}".encode()).hexdigest()
            self.id = f"{self.provider}_{identifier}"

        return self


class SocialProvider(BaseProvider):
    provider: Literal[
        "google",
        "facebook",
        "gitlab",
        "slack",
        "spotify",
        "discord",
        "twitch",
        "netid",
        "yander",
        "vk",
        "dingtalk",
    ]
    client_secret: Secret


class GithubProvider(BaseProvider):
    provider: Literal["github"]
    client_secret: Secret
    scope: list[str] = ["user:email"]

    @field_validator("scope", mode="before")
    @classmethod
    def deserialize_scope(cls, v: Optional[str]) -> list[str]:
        v = v or "user:email"
        return v.split()


class MicrosoftProvider(BaseProvider):
    provider: Literal["microsoft"]
    client_secret: Secret
    microsoft_tenant: str = Field(
        validation_alias=AliasChoices("microsoft_tenant", "microsoft_tenant_id"),
        serialization_alias="microsoft_tenant",
    )

    @model_validator(mode="after")
    def deserialize_id(self) -> Self:
        if not self.id:
            identifier = hashlib.sha1(
                f"{self.client_id}_{self.microsoft_tenant}".encode()
            ).hexdigest()
            self.id = f"{self.provider}_{identifier}"

        return self


class AppleProvider(BaseProvider):
    provider: Literal["apple"]
    apple_team_id: str
    apple_private_key_id: str
    apple_private_key: Secret


Provider = Annotated[
    Union[
        GenericProvider,
        SocialProvider,
        GithubProvider,
        MicrosoftProvider,
        AppleProvider,
    ],
    Field(discriminator="provider"),
]


class Providers(RootModel[list[Provider]]):
    def __iter__(self) -> Iterator[Provider]:
        yield from self.root

    def __getitem__(self, idx: int) -> Provider:
        return self.root[idx]

    def __len__(self) -> int:
        return len(self.root)


class RequirerProvider(BaseModel):
    provider_id: str
    redirect_uri: str


class RequirerProviders(RootModel[list[RequirerProvider]]):
    def __iter__(self) -> Iterator[RequirerProvider]:
        yield from self.root

    def __getitem__(self, idx: int) -> RequirerProvider:
        return self.root[idx]

    def __len__(self) -> int:
        return len(self.root)


class RelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""

    def snapshot(self) -> dict:
        """Save event."""
        return {}

    def restore(self, snapshot: dict) -> None:
        """Restore event."""
        pass


class RedirectURIChangedEvent(EventBase):
    """Event to notify the charm that the redirect_uri changed."""

    def __init__(self, handle: Handle, redirect_uri: str) -> None:
        super().__init__(handle)
        self.redirect_uri = redirect_uri

    def snapshot(self) -> dict:
        """Save redirect_uri."""
        return {"redirect_uri": self.redirect_uri}

    def restore(self, snapshot: dict) -> None:
        """Restore redirect_uri."""
        self.redirect_uri = snapshot["redirect_uri"]


class ExternalIdpProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `ExternalIdpProvider`."""

    ready = EventSource(RelationReadyEvent)
    redirect_uri_changed = EventSource(RedirectURIChangedEvent)


class ExternalIdpProvider(Object):
    """Forward client configurations to Identity Broker."""

    on = ExternalIdpProviderEvents()

    def __init__(self, charm: CharmBase, relation_name: str = DEFAULT_RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(events.relation_joined, self._on_provider_endpoint_relation_joined)
        self.framework.observe(
            events.relation_changed, self._on_provider_endpoint_relation_changed
        )
        self.framework.observe(
            events.relation_departed, self._on_provider_endpoint_relation_departed
        )

    def _on_provider_endpoint_relation_joined(self, event: RelationJoinedEvent) -> None:
        self.on.ready.emit()

    def _on_provider_endpoint_relation_changed(self, event: RelationChangedEvent) -> None:
        if not event.app:
            return

        relation_data = event.relation.data[event.app]
        if not (providers := relation_data.get("providers")):
            return

        if not (data := RequirerProviders.model_validate(json.loads(providers))):
            return

        self.on.redirect_uri_changed.emit(redirect_uri=data[0].redirect_uri)

    def _on_provider_endpoint_relation_departed(self, event: RelationDepartedEvent) -> None:
        self.on.redirect_uri_changed.emit(redirect_uri="")

    def is_ready(self) -> bool:
        """Checks if the relation is ready."""
        return self._charm.model.get_relation(self._relation_name) is not None

    def create_providers(self, providers: Providers) -> None:
        if not self._charm.unit.is_leader():
            return

        for relation in self._charm.model.relations[self._relation_name]:
            relation.data[self._charm.app]["providers"] = providers.model_dump_json()

    def remove_provider(self) -> None:
        if not self._charm.unit.is_leader():
            return

        for relation in self._charm.model.relations[self._relation_name]:
            relation.data[self._charm.app].clear()

    def get_redirect_uri(self, relation_id: Optional[int] = None) -> Optional[str]:
        """Get the kratos client's redirect_uri."""
        if not self.model.unit.is_leader():
            return None

        try:
            relation = self.model.get_relation(
                relation_name=self._relation_name, relation_id=relation_id
            )
        except TooManyRelatedAppsError:
            raise RuntimeError("More than one relations are defined. Please provide a relation_id")

        if not relation or not relation.app:
            return None

        relation_data = relation.data[relation.app]
        if not (providers := relation_data.get("providers")):
            return None

        if not (data := RequirerProviders.model_validate(json.loads(providers))):
            return None

        return data[0].redirect_uri

    @staticmethod
    def validate_provider_config(configurations: list[Mapping]) -> Optional[Providers]:
        """Validate the OIDC provider configuration."""
        try:
            providers = Providers.model_validate(configurations)
        except ValidationError as e:
            logger.error("External IdP provider configuration invalid: %s", e)
            return None

        return providers


class ClientConfigChangedEvent(EventBase):
    """Event to notify the charm that a provider's client config changed."""

    def __init__(self, handle: Handle, provider: Provider) -> None:
        super().__init__(handle)
        self.client_id = provider.client_id
        self.provider = provider.provider
        self.provider_id = provider.id
        self.relation_id = provider.relation_id

    def snapshot(self) -> dict:
        """Save event."""
        return {
            "client_id": self.client_id,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot: dict) -> None:
        """Restore event."""
        self.client_id = snapshot["client_id"]
        self.provider = snapshot["provider"]
        self.provider_id = snapshot["provider_id"]
        self.relation_id = snapshot["relation_id"]


class ClientConfigRemovedEvent(EventBase):
    """Event to notify the charm that a provider's client config was removed."""

    def __init__(self, handle: Handle, relation_id: str) -> None:
        super().__init__(handle)
        self.relation_id = relation_id

    def snapshot(self) -> dict:
        """Save event."""
        return {
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot: dict) -> None:
        """Restore event."""
        self.relation_id = snapshot["relation_id"]


class ExternalIdpRequirerEvents(ObjectEvents):
    """Event descriptor for events raised by `ExternalIdpRequirerEvents`."""

    client_config_changed = EventSource(ClientConfigChangedEvent)
    client_config_removed = EventSource(ClientConfigRemovedEvent)


class ExternalIdpRequirer(Object):
    """Receive the External Idp configurations for Kratos."""

    on = ExternalIdpRequirerEvents()

    def __init__(self, charm: CharmBase, relation_name: str = DEFAULT_RELATION_NAME) -> None:
        super().__init__(charm, relation_name)
        self._charm = charm
        self._relation_name = relation_name

        events = self._charm.on[relation_name]
        self.framework.observe(
            events.relation_changed,
            self._on_provider_endpoint_relation_changed,
        )
        self.framework.observe(
            events.relation_broken,
            self._on_provider_endpoint_relation_broken,
        )

    @property
    def relations(self) -> list[Relation]:
        return [
            relation
            for relation in self._charm.model.relations[self._relation_name]
            if relation.active
        ]

    def _on_provider_endpoint_relation_changed(self, event: RelationEvent) -> None:
        if not (app := event.app):
            return

        relation_data = event.relation.data[app]
        if not (providers_json := relation_data.get("providers")):
            self.on.client_config_removed.emit(event.relation.id)
            return

        providers = Providers.model_validate_json(providers_json)

        provider = providers[0]
        provider.relation_id = event.relation.id
        self.on.client_config_changed.emit(provider)

    def _on_provider_endpoint_relation_broken(self, event: RelationBrokenEvent) -> None:
        self.on.client_config_removed.emit(event.relation.id)

    def update_registered_provider(self, providers: RequirerProviders, relation_id: int) -> None:
        if not self._charm.unit.is_leader():
            return

        if not (
            relation := self.model.get_relation(
                relation_name=self._relation_name, relation_id=relation_id
            )
        ):
            return

        relation.data[self.model.app].update({"providers": providers.model_dump_json()})

    def remove_registered_provider(self, relation_id: int) -> None:
        if not self._charm.unit.is_leader():
            return

        if not (
            relation := self.model.get_relation(
                relation_name=self._relation_name, relation_id=relation_id
            )
        ):
            return

        relation.data[self.model.app].clear()

    def get_providers_from_relation(self, relation: Relation) -> Optional[Providers]:
        if not relation.app:
            return None

        relation_data = relation.data[relation.app]
        if not (providers_json := relation_data.get("providers")):
            return None

        providers = Providers.model_validate_json(providers_json)
        for provider in providers:
            provider.relation_id = relation.id

        return providers

    def get_providers(self) -> list[Provider]:
        return [
            provider
            for relation in self.relations
            for provider in self.get_providers_from_relation(relation) or []
        ]
