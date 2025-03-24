#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Interface library for Kratos external OIDC providers.

This library wraps relation endpoints using the `kratos-external-idp` interface
and provides a Python API for both requesting Kratos to register the client credentials
and for communicating with an external provider.

## Getting Started

To get started using the library, you just need to fetch the library using `charmcraft`.

```shell
cd some-charm
charmcraft fetch-lib charms.kratos_external_idp_integrator.v0.kratos_external_provider
```

To use the library from the provider side (KratosExternalIdpIntegrator):

In the `metadata.yaml` of the charm, add the following:
```yaml
provides:
    kratos-external-idp:
        interface: external_provider
        limit: 1
```

Then, to initialise the library:

```python
from charms.kratos_external_idp_integrator.v0.kratos_external_provider import (
    ExternalIdpProvider, InvalidConfigError
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
        try:
            self.external_idp_provider.validate_provider_config(self.config)
        except InvalidConfigError as e:
            self.unit.status = BlockedStatus(f"Invalid configuration: {e.args[0]}")

        # ...

    def _on_redirect_uri_changed(self, event):
        logger.info(f"The client's redirect_uri changed to {event.redirect_uri}")
        self._stored.redirect_uri = event.redirect_uri
        self._on_update_status(event)

    def _on_ready(self, event):
        if not isinstance(self.unit.status, BlockedStatus):
            self.external_idp_provider.create_provider(self.config)
```

To use the library from the requirer side (Kratos):

In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
    kratos-external-idp:
        interface: external_provider
```

Then, to initialise the library:

```python
from charms.kratos_external_idp_integrator.v0.kratos_external_provider import (
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

        self.external_provider.set_relation_registered_provider(
            some_redirect_uri, event.provider_id, event.relation_id
        )
```
"""

import base64
import hashlib
import inspect
import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Type

import jsonschema
from ops.charm import (
    CharmBase,
    RelationChangedEvent,
    RelationDepartedEvent,
    RelationEvent,
    RelationJoinedEvent,
)
from ops.framework import EventBase, EventSource, Handle, Object, ObjectEvents
from ops.model import Relation, TooManyRelatedAppsError

# The unique Charmhub library identifier, never change it
LIBID = "33040051de7f43a8bb43349f2b037dfc"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 11

PYDEPS = ["jsonschema"]

DEFAULT_RELATION_NAME = "kratos-external-idp"
logger = logging.getLogger(__name__)

PROVIDER_PROVIDERS_JSON_SCHEMA = {
    "type": "array",
    "items": {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "provider": {
                        "type": "string",
                        "enum": [
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
                        ],
                    },
                    "client_id": {"type": "string"},
                    "client_secret": {"type": "string"},
                    "secret_backend": {"type": "string"},
                    "issuer_url": {"type": "string"},
                    "tenant_id": {"type": "string"},
                    "private_key": {"type": "string"},
                    "private_key_id": {"type": "string"},
                    "scope": {"type": "string"},
                    "team_id": {"type": "string"},
                    "provider_id": {"type": "string"},
                    "label": {"type": "string"},
                    "jsonnet_mapper": {"type": "string"},
                },
                "additionalProperties": True,
            },
        ],
    },
}

PROVIDER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "providers": PROVIDER_PROVIDERS_JSON_SCHEMA,
    },
}

REQUIRER_PROVIDERS_JSON_SCHEMA = {
    "type": "array",
    "items": {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "provider_id": {"type": "string"},
                    "redirect_uri": {"type": "string"},
                },
                "additionalProperties": True,
            },
        ]
    },
}

REQUIRER_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "providers": REQUIRER_PROVIDERS_JSON_SCHEMA,
    },
}


class InvalidConfigError(Exception):
    """Internal exception that is raised if the charm config is not valid."""


class DataValidationError(RuntimeError):
    """Raised when data validation fails on relation data."""


def _load_data(data: Dict, schema: Dict) -> Dict:
    """Parses nested fields and checks whether `data` matches `schema`."""
    if "providers" not in data:
        return {"providers": []}

    data = dict(data)
    try:
        data["providers"] = json.loads(data["providers"])
    except json.JSONDecodeError as e:
        raise DataValidationError(f"Failed to decode relation json: {e}")

    _validate_data(data, schema)
    return data


def _dump_data(data: Dict, schema: Dict) -> Dict:
    _validate_data(data, schema)

    data = dict(data)
    try:
        data["providers"] = json.dumps(data["providers"])
    except json.JSONDecodeError as e:
        raise DataValidationError(f"Failed to encode relation json: {e}")
    return data


def _validate_data(data: Dict, schema: Dict) -> None:
    """Checks whether `data` matches `schema`.

    Will raise DataValidationError if the data is not valid, else return None.
    """
    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise DataValidationError(data, schema) from e


class BaseProviderConfigHandler:
    """The base class for parsing a provider's config."""

    mandatory_fields = {"provider", "client_id", "secret_backend"}
    optional_fields = {"provider_id", "jsonnet_mapper", "label", "scope"}
    excluded_fields = {"enabled"}
    default_scope = "profile email address phone"
    providers: List[str] = []

    @classmethod
    def validate_config(cls, config: Mapping) -> Dict:
        """Validate and sanitize the user provided config."""
        config_keys = set(config.keys())
        provider = config["provider"]
        if provider not in cls.providers:
            raise ValueError(f"Invalid provider, allowed providers are: {cls.providers}")

        for key in cls.mandatory_fields:
            if not config.get(key, None):
                raise InvalidConfigError(
                    f"Missing required configuration '{key}' for provider '{config['provider']}'"
                )
            config_keys.remove(key)

        for key in cls.optional_fields:
            config_keys.discard(key)

        if config["secret_backend"] not in ["relation", "secret", "vault"]:
            raise InvalidConfigError(
                f"Invalid value {config['secret_backend']} for `secret_backend` "
                "allowed values are: ['relation', 'secret', 'vault']"
            )

        for key in config_keys:
            if key not in cls.excluded_fields:
                logger.warn(f"Invalid config '{key}' for provider '{provider}' will be ignored")

        return {key: value for key, value in config.items() if key not in config_keys}

    @classmethod
    def handle_config(cls, config: Mapping) -> List:
        """Validate the config and transform it in the relation databag expected format."""
        config = cls.validate_config(config)
        return cls.parse_config(config)

    @classmethod
    def parse_config(cls, config: Dict) -> List:
        """Parse the user provided config into the relation databag expected format."""
        ret = {
            "client_id": config["client_id"],
            "provider": config["provider"],
            "secret_backend": config["secret_backend"],
            "scope": config.get("scope", cls.default_scope),
        }
        ret.update({k: config[k] for k in cls.optional_fields if k in config})
        ret.update(cls._parse_provider_config(config))
        return [ret]

    @classmethod
    def _parse_provider_config(cls, config: Dict) -> Dict:
        """Create the provider specific config."""
        raise NotImplementedError()


class GenericConfigHandler(BaseProviderConfigHandler):
    """The class for parsing a 'generic' provider's config."""

    mandatory_fields = BaseProviderConfigHandler.mandatory_fields | {"client_secret", "issuer_url"}
    providers = ["generic", "auth0"]

    @classmethod
    def _parse_provider_config(cls, config: Dict) -> Dict:
        return {
            "client_secret": config["client_secret"],
            "issuer_url": config["issuer_url"],
        }


class SocialConfigHandler(BaseProviderConfigHandler):
    """The class for parsing a social provider's config."""

    mandatory_fields = BaseProviderConfigHandler.mandatory_fields | {"client_secret"}
    providers = [
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

    @classmethod
    def _parse_provider_config(cls, config: Dict) -> Dict:
        return {
            "client_secret": config["client_secret"],
        }


class MicrosoftConfigHandler(SocialConfigHandler):
    """The class for parsing a 'microsoft' provider's config."""

    mandatory_fields = SocialConfigHandler.mandatory_fields | {
        "microsoft_tenant_id",
    }
    providers = ["microsoft"]

    @classmethod
    def _parse_provider_config(cls, config: Dict) -> Dict:
        return {
            "client_secret": config["client_secret"],
            "tenant_id": config["microsoft_tenant_id"],
        }

    @classmethod
    def _parse_relation_data(cls, data: Dict) -> Dict:
        return {
            "client_secret": data["client_secret"],
            "tenant_id": data["tenant_id"],
        }


class GithubConfigHandler(SocialConfigHandler):
    """The class for parsing a 'github' provider's config."""

    default_scope = "user:email"
    providers = ["github"]


class AppleConfigHandler(BaseProviderConfigHandler):
    """The class for parsing an 'apple' provider's config."""

    mandatory_fields = BaseProviderConfigHandler.mandatory_fields | {
        "apple_team_id",
        "apple_private_key_id",
        "apple_private_key",
    }
    _secret_fields = ["private_key"]
    providers = ["apple"]

    @classmethod
    def _parse_provider_config(cls, config: Dict) -> Dict:
        return {
            "team_id": config["apple_team_id"],
            "private_key_id": config["apple_private_key_id"],
            "private_key": config["apple_private_key"],
        }


_config_handlers = [
    GenericConfigHandler,
    SocialConfigHandler,
    MicrosoftConfigHandler,
    GithubConfigHandler,
    AppleConfigHandler,
]
allowed_providers = {
    provider: handler for handler in _config_handlers for provider in handler.providers
}


def get_provider_config_handler(config: Mapping) -> Type[BaseProviderConfigHandler]:
    """Get the config handler for this provider."""
    provider = config.get("provider")
    if provider not in allowed_providers:
        raise InvalidConfigError(
            "Required configuration 'provider' MUST be one of the following: "
            + ", ".join(allowed_providers)
        )
    return allowed_providers[provider]


class RelationReadyEvent(EventBase):
    """Event to notify the charm that the relation is ready."""

    def snapshot(self) -> Dict:
        """Save event."""
        return {}

    def restore(self, snapshot: Dict) -> None:
        """Restore event."""
        pass


class RedirectURIChangedEvent(EventBase):
    """Event to notify the charm that the redirect_uri changed."""

    def __init__(self, handle: Handle, redirect_uri: str) -> None:
        super().__init__(handle)
        self.redirect_uri = redirect_uri

    def snapshot(self) -> Dict:
        """Save redirect_uri."""
        return {"redirect_uri": self.redirect_uri}

    def restore(self, snapshot: Dict) -> None:
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
        data = event.relation.data[event.app]
        data = _load_data(data, REQUIRER_JSON_SCHEMA)
        providers = data["providers"]

        if len(providers) == 0:
            return
        redirect_uri = providers[0].get("redirect_uri")
        self.on.redirect_uri_changed.emit(redirect_uri=redirect_uri)

    def _on_provider_endpoint_relation_departed(self, event: RelationDepartedEvent) -> None:
        self.on.redirect_uri_changed.emit(redirect_uri="")

    def is_ready(self) -> bool:
        """Checks if the relation is ready."""
        return self._charm.model.get_relation(self._relation_name) is not None

    def create_provider(self, config: Mapping) -> None:
        """Use the configuration to create the relation databag."""
        if not self._charm.unit.is_leader():
            return

        config = self._handle_config(config)
        return self._set_provider_data(config)

    def remove_provider(self) -> None:
        """Remove the provider config to the relation databag."""
        if not self._charm.unit.is_leader():
            return

        # Do we need to iterate on the relations? There should never be more
        # than one
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

        data = relation.data[relation.app]
        data = _load_data(data, REQUIRER_JSON_SCHEMA)
        providers = data["providers"]

        if len(providers) == 0:
            return None

        return providers[0].get("redirect_uri")

    def validate_provider_config(self, config: Mapping) -> None:
        """Validate the provider config.

        Raises InvalidConfigError if config is invalid.
        """
        self._validate_config(config)

    def _handle_config(self, config: Mapping) -> List:
        handler = get_provider_config_handler(config)
        return handler.handle_config(config)

    def _validate_config(self, config: Mapping) -> None:
        handler = get_provider_config_handler(config)
        handler.validate_config(config)

    def _set_provider_data(self, provider_config: List) -> None:
        self._create_secrets(provider_config)
        # Do we need to iterate on the relations? There should never be more
        # than one
        for relation in self._charm.model.relations[self._relation_name]:
            relation.data[self._charm.app]["providers"] = json.dumps(provider_config)

    def _create_secrets(self, provider_config: List) -> None:
        for conf in provider_config:
            backend = conf["secret_backend"]

            if backend == "relation":
                pass
            elif backend == "secret":
                raise NotImplementedError()
            elif backend == "vault":
                raise NotImplementedError()
            else:
                raise ValueError(f"Invalid backend: {backend}")


@dataclass
class Provider:
    """Class for describing an external provider."""

    client_id: str
    provider: str
    relation_id: Optional[str] = None
    scope: str = "profile email address phone"
    label: Optional[str] = None
    client_secret: Optional[str] = None
    issuer_url: Optional[str] = None
    tenant_id: Optional[str] = None
    microsoft_tenant: Optional[str] = None
    team_id: Optional[str] = None
    private_key_id: Optional[str] = None
    private_key: Optional[str] = None
    jsonnet_mapper: Optional[str] = None
    id: Optional[str] = None

    @property
    def provider_id(self) -> str:
        """Returns a unique ID for the client credentials of the provider."""
        if self.id:
            return self.id

        if self.issuer_url:
            id = hashlib.sha1(f"{self.client_id}_{self.issuer_url}".encode()).hexdigest()
        elif self.get_microsoft_tenant():
            id = hashlib.sha1(f"{self.client_id}_{self.tenant_id}".encode()).hexdigest()
        else:
            id = hashlib.sha1(self.client_id.encode()).hexdigest()
        return f"{self.provider}_{id}"

    @provider_id.setter
    def provider_id(self, val) -> None:
        self.id = val

    def get_scope(self) -> list:
        if isinstance(self.scope, str):
            return self.scope.split(" ")
        elif isinstance(self.scope, list):
            return self.scope
        else:
            raise ValueError(f"scope must be `list` or `str`, but `{type(self.scope)}` provided")

    def get_microsoft_tenant(self) -> str:
        return self.tenant_id or self.microsoft_tenant

    def config(self) -> Dict:
        """Generate Kratos config for this provider."""
        ret = {
            "id": self.provider_id,
            "client_id": self.client_id,
            "provider": self.provider,
            "label": self.label or self.provider,
            "client_secret": self.client_secret,
            "issuer_url": self.issuer_url,
            "scope": self.get_scope(),
            "mapper_url": (
                f"base64://{base64.b64encode(self.jsonnet_mapper.encode()).decode()}"
                if self.jsonnet_mapper
                else None
            ),
            "microsoft_tenant": self.get_microsoft_tenant(),
            "apple_team_id": self.team_id,
            "apple_private_key_id": self.private_key_id,
            "apple_private_key": self.private_key,
        }
        return {k: v for k, v in ret.items() if v}

    @classmethod
    def from_dict(cls, dic: Dict) -> "Provider":
        """Generate Provider instance from dict."""
        if provider_id := dic.get("provider_id"):
            dic["id"] = provider_id
        return cls(**{k: v for k, v in dic.items() if k in inspect.signature(cls).parameters})


class ClientConfigChangedEvent(EventBase):
    """Event to notify the charm that a provider's client config changed."""

    def __init__(self, handle: Handle, provider: Provider) -> None:
        super().__init__(handle)
        self.client_id = provider.client_id
        self.provider = provider.provider
        self.provider_id = provider.provider_id
        self.relation_id = provider.relation_id

    def snapshot(self) -> Dict:
        """Save event."""
        return {
            "client_id": self.client_id,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot: Dict) -> None:
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

    def snapshot(self) -> Dict:
        """Save event."""
        return {
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot: Dict) -> None:
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
            events.relation_changed, self._on_provider_endpoint_relation_changed
        )
        self.framework.observe(
            events.relation_departed, self._on_provider_endpoint_relation_changed
        )

    def _on_provider_endpoint_relation_changed(self, event: RelationEvent) -> None:
        if not event.app:
            return

        data = event.relation.data[event.app]
        data = _load_data(data, PROVIDER_JSON_SCHEMA)
        providers = data["providers"]

        if len(providers) == 0:
            self.on.client_config_removed.emit(event.relation.id)
            return

        p = self._get_provider(providers[0], event.relation)
        self.on.client_config_changed.emit(p)

    def set_relation_registered_provider(
        self, redirect_uri: str, provider_id: str, relation_id: int
    ) -> None:
        """Update the relation databag."""
        if not self._charm.unit.is_leader():
            return

        data = {
            "providers": [
                {
                    "redirect_uri": redirect_uri,
                    "provider_id": provider_id,
                }
            ]
        }

        data = _dump_data(data, REQUIRER_JSON_SCHEMA)

        relation = self.model.get_relation(
            relation_name=self._relation_name, relation_id=relation_id
        )
        if not relation:
            return
        relation.data[self.model.app].update(data)

    def remove_relation_registered_provider(self, relation_id: int) -> None:
        """Delete the provider info from the databag."""
        if not self._charm.unit.is_leader():
            return

        relation = self.model.get_relation(
            relation_name=self._relation_name, relation_id=relation_id
        )
        if not relation:
            return
        relation.data[self.model.app].clear()

    def get_providers(self) -> List:
        """Iterate over the relations and fetch all providers."""
        providers = []
        # For each relation get the client credentials and compile them into a
        # single object
        for relation in self.model.relations[self._relation_name]:
            if not relation.app:
                continue
            data = relation.data[relation.app]
            data = _load_data(data, PROVIDER_JSON_SCHEMA)
            for p in data["providers"]:
                provider = self._get_provider(p, relation)
                providers.append(provider)

        return providers

    def _get_provider(self, provider: Dict, relation: Relation) -> Provider:
        provider = self._extract_secrets(provider)
        provider["relation_id"] = relation.id
        provider = Provider.from_dict(provider)
        return provider

    def _extract_secrets(self, data: Dict) -> Dict:
        backend = data["secret_backend"]

        if backend == "relation":
            pass
        elif backend == "secret":
            raise NotImplementedError()
        elif backend == "vault":
            raise NotImplementedError()
        else:
            raise ValueError(f"Invalid backend: {backend}")
        return data
