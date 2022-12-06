#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""# Interface library for Kratos external OIDC providers.

This library wraps relation endpoints using the `kratos-external-idp` interface
and provides a Python API for both requesting Kratos to register the the client credentials for
communicating with an external provider.

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

Next add the `jsonschema` python package to your charm's `requirements.txt`, so that the
library can validate the incoming relation databags.

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

import hashlib
import inspect
import json
import logging
from collections import defaultdict
from dataclasses import dataclass

import jsonschema
from ops.framework import EventBase, EventSource, Object, ObjectEvents

# The unique Charmhub library identifier, never change it
LIBID = "33040051de7f43a8bb43349f2b037dfc"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

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
                    "team_id": {"type": "string"},
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


def _load_data(data, schema):
    """Parses nested fields and checks whether `data` matches `schema`."""
    if "providers" not in data:
        return dict(providers=[])

    data = dict(data)
    try:
        data["providers"] = json.loads(data["providers"])
    except json.JSONDecodeError as e:
        raise DataValidationError(f"Failed to decode relation json: {e}")

    _validate_data(data, schema)
    return data


def _dump_data(data, schema):
    _validate_data(data, schema)

    data = dict(data)
    try:
        data["providers"] = json.dumps(data["providers"])
    except json.JSONDecodeError as e:
        raise DataValidationError(f"Failed to encode relation json: {e}")
    return data


def _validate_data(data, schema):
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
    providers = []

    @classmethod
    def validate_config(cls, config):
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

        if config["secret_backend"] not in ["relation", "secret", "vault"]:
            raise InvalidConfigError(
                f"Invalid value {config['secret_backend']} for `secret_backend` "
                "allowed values are: ['relation', 'secret', 'vault']"
            )

        for key in config_keys:
            logger.warn(f"Invalid config '{key}' for provider '{provider}' will be ignored")

        return {key: value for key, value in config.items() if key not in config_keys}

    @classmethod
    def handle_config(cls, config):
        """Validate the config and transform it in the relation databag expected format."""
        config = cls.validate_config(config)
        return cls.parse_config(config)

    @classmethod
    def parse_config(cls, config):
        """Parse the user provided config into the relation databag expected format."""
        return [
            {
                "client_id": config["client_id"],
                "provider": config["provider"],
                "secret_backend": config["secret_backend"],
                **cls._parse_provider_config(config),
            }
        ]

    @classmethod
    def _parse_provider_config(cls, config):
        """Create the provider specific config."""
        raise NotImplementedError()


class GenericConfigHandler(BaseProviderConfigHandler):
    """The class for parsing a 'generic' provider's config."""

    mandatory_fields = BaseProviderConfigHandler.mandatory_fields | {"client_secret", "issuer_url"}
    providers = ["generic", "auth0"]

    @classmethod
    def _parse_provider_config(cls, config):
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
        "github",
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
    def _parse_provider_config(cls, config):
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
    def _parse_provider_config(cls, config):
        return {
            "client_secret": config["client_secret"],
            "tenant_id": config["microsoft_tenant_id"],
        }

    @classmethod
    def _parse_relation_data(cls, data):
        return {
            "client_secret": data["client_secret"],
            "tenant_id": data["tenant_id"],
        }


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
    def _parse_provider_config(cls, config):
        return {
            "team_id": config["apple_team_id"],
            "private_key_id": config["apple_private_key_id"],
            "private_key": config["apple_private_key"],
        }


_config_handlers = [
    GenericConfigHandler,
    SocialConfigHandler,
    MicrosoftConfigHandler,
    AppleConfigHandler,
]
allowed_providers = {
    provider: handler for handler in _config_handlers for provider in handler.providers
}


def get_provider_config_handler(config):
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

    def snapshot(self):
        """Save event."""
        return {}

    def restore(self, snapshot):
        """Restore event."""
        pass


class RedirectURIChangedEvent(EventBase):
    """Event to notify the charm that the redirect_uri changed."""

    def __init__(self, handle, redirect_uri):
        super().__init__(handle)
        self.redirect_uri = redirect_uri

    def snapshot(self):
        """Save redirect_uri."""
        return {"redirect_uri": self.redirect_uri}

    def restore(self, snapshot):
        """Restore redirect_uri."""
        self.redirect_uri = snapshot["redirect_uri"]


class ExternalIdpProviderEvents(ObjectEvents):
    """Event descriptor for events raised by `ExternalIdpProvider`."""

    ready = EventSource(RelationReadyEvent)
    redirect_uri_changed = EventSource(RedirectURIChangedEvent)


class ExternalIdpProvider(Object):
    """Forward client configurations to Identity Broker."""

    on = ExternalIdpProviderEvents()

    def __init__(self, charm, relation_name=DEFAULT_RELATION_NAME):
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

    def _on_provider_endpoint_relation_joined(self, event):
        self.on.ready.emit()

    def _on_provider_endpoint_relation_changed(self, event):
        data = event.relation.data[event.app]
        data = _load_data(data, REQUIRER_JSON_SCHEMA)
        providers = data["providers"]

        if len(providers) == 0:
            return
        redirect_uri = providers[0].get("redirect_uri")
        self.on.redirect_uri_changed.emit(redirect_uri=redirect_uri)

    def _on_provider_endpoint_relation_departed(self, event):
        self.on.redirect_uri_changed.emit(redirect_uri="")

    def is_ready(self):
        """Checks if the relation is ready."""
        return self._charm.model.get_relation(self._relation_name)

    def create_provider(self, config):
        """Use the configuration to create the relation databag."""
        if not self._charm.unit.is_leader():
            return

        config = self._handle_config(config)
        return self._set_provider_data(config)

    def remove_provider(self):
        """Remove the provider config to the relation databag."""
        if not self._charm.unit.is_leader():
            return

        # Do we need to iterate on the relations? There should never be more
        # than one
        for relation in self._charm.model.relations[self._relation_name]:
            relation.data[self._charm.app].clear()

    def validate_provider_config(self, config):
        """Validate the provider config.

        Raises InvalidConfigError is config is invalid.
        """
        self._validate_config(config)

    def _handle_config(self, config):
        handler = get_provider_config_handler(config)
        return handler.handle_config(config)

    def _validate_config(self, config):
        handler = get_provider_config_handler(config)
        handler.validate_config(config)

    def _set_provider_data(self, provider_config):
        self._create_secrets(provider_config)
        # Do we need to iterate on the relations? There should never be more
        # than one
        for relation in self._charm.model.relations[self._relation_name]:
            relation.data[self._charm.app].update(providers=json.dumps(provider_config))

    def _create_secrets(self, provider_config):
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
    relation_id: str
    client_secret: str = None
    issuer_url: str = None
    tenant_id: str = None
    team_id: str = None
    private_key_id: str = None
    private_key: str = None

    @property
    def provider_id(self):
        """Returns a unique ID for the client credentials of the provider."""
        if self.issuer_url:
            id = hashlib.sha1(f"{self.client_id}_{self.issuer_url}".encode()).hexdigest()
        elif self.tenant_id:
            id = hashlib.sha1(f"{self.client_id}_{self.tenant_id}".encode()).hexdigest()
        else:
            id = hashlib.sha1(self.client_id.encode()).hexdigest()
        return f"{self.provider}_{id}"

    def config(self):
        """Generate Kratos config for this provider."""
        ret = {
            "id": self.provider_id,
            "client_id": self.client_id,
            "provider": self.provider,
            "client_secret": self.client_secret,
            "issuer_url": self.issuer_url,
            "microsoft_tenant": self.tenant_id,
            "apple_team_id": self.team_id,
            "apple_private_key_id": self.private_key_id,
            "apple_private_key": self.private_key,
        }
        return {k: v for k, v in ret.items() if v}

    @classmethod
    def from_dict(cls, dic):
        """Generate Provider instance from dict."""
        return cls(**{k: v for k, v in dic.items() if k in inspect.signature(cls).parameters})


class ClientConfigChangedEvent(EventBase):
    """Event to notify the charm that a provider's client config changed."""

    def __init__(self, handle, provider):
        super().__init__(handle)
        self.client_id = provider.client_id
        self.provider = provider.provider
        self.provider_id = provider.provider_id
        self.relation_id = provider.relation_id

    def snapshot(self):
        """Save event."""
        return {
            "client_id": self.client_id,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "relation_id": self.relation_id,
        }

    def restore(self, snapshot):
        """Restore event."""
        self.client_id = snapshot["client_id"]
        self.provider = snapshot["provider"]
        self.provider_id = snapshot["provider_id"]
        self.relation_id = snapshot["relation_id"]


class ExternalIdpRequirerEvents(ObjectEvents):
    """Event descriptor for events raised by `ExternalIdpRequirerEvents`."""

    client_config_changed = EventSource(ClientConfigChangedEvent)


class ExternalIdpRequirer(Object):
    """Receive the External Idp configurations for Kratos."""

    on = ExternalIdpRequirerEvents()

    def __init__(self, charm, relation_name=DEFAULT_RELATION_NAME):
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

    def _on_provider_endpoint_relation_changed(self, event):
        data = event.relation.data[event.app]
        data = _load_data(data, PROVIDER_JSON_SCHEMA)
        providers = data["providers"]

        if len(providers) == 0:
            return

        _, p = self._get_provider(providers[0], event.relation)
        self.on.client_config_changed.emit(p)

    def set_relation_registered_provider(self, redirect_uri, provider_id, relation_id):
        """Update the relation databag."""
        data = dict(
            providers=[
                dict(
                    redirect_uri=redirect_uri,
                    provider_id=provider_id,
                )
            ]
        )

        data = _dump_data(data, REQUIRER_JSON_SCHEMA)

        relation = self.model.get_relation(
            relation_name=self._relation_name, relation_id=relation_id
        )
        relation.data[self.model.app].update(data)

    def get_providers(self):
        """Iterate over the relations and fetch all providers."""
        providers = defaultdict(list)
        providers = []
        # For each relation get the client credentials and compile them into a
        # single object
        for relation in self.model.relations[self._relation_name]:
            data = relation.data[relation.app]
            data = _load_data(data, PROVIDER_JSON_SCHEMA)
            for p in data["providers"]:
                provider_type, provider = self._get_provider(p, relation)
                # providers[provider_type].append(provider)
                providers.append(provider)

        return providers

    def _get_provider(self, provider, relation):
        provider = self._extract_secrets(provider)
        provider["relation_id"] = relation.id
        provider = Provider.from_dict(provider)
        provider_type = provider.provider
        return provider_type, provider

    def _extract_secrets(self, data):
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
