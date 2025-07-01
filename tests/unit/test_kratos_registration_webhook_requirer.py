# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from typing import Any, Dict, Generator, List

import pytest
from charms.kratos.v0.kratos_registration_webhook import (
    KratosRegistrationWebhookRequirer,
    ProviderData,
    ReadyEvent,
    UnavailableEvent,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: requirer-tester
requires:
  kratos-registration-webhook:
    interface: kratos_registration_webhook
"""


class KratosRegistrationWebhookRequirerCharm(CharmBase):
    def __init__(self, *args: Any) -> None:
        super().__init__(*args)
        self.kratos_registration_webhook = KratosRegistrationWebhookRequirer(self)
        self.events: List = []

        self.framework.observe(self.kratos_registration_webhook.on.ready, self._record_event)
        self.framework.observe(self.kratos_registration_webhook.on.unavailable, self._record_event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def auth_config_value() -> str:
    return "token"


@pytest.fixture()
def provider_data() -> ProviderData:
    data = ProviderData(
        url="https://path/to/hook",
        body="body",
        method="POST",
        response_ignore=True,
        response_parse=True,
        auth_type="api_key",
        auth_config_name="Authorization",
        auth_config_in="header",
    )
    return data


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(KratosRegistrationWebhookRequirerCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


def dict_to_relation_data(dic: Dict) -> Dict:
    return {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in dic.items()}


def test_data_in_relation_bag(
    harness: Harness, provider_data: ProviderData, auth_config_value: str
) -> None:
    relation_id = harness.add_relation("kratos-registration-webhook", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    secret_id = harness.add_model_secret("provider", {"auth-config-value": auth_config_value})
    harness.grant_secret(secret_id, "requirer-tester")
    provider_data.auth_config_value_secret = secret_id

    harness.update_relation_data(
        relation_id,
        "provider",
        provider_data.model_dump(exclude_none=True),
    )

    relation_data = harness.charm.kratos_registration_webhook.consume_relation_data(relation_id)
    provider_data.auth_config_value = auth_config_value

    assert isinstance(harness.charm.events[0], ReadyEvent)
    assert relation_data.auth_enabled is True
    assert relation_data == provider_data


def test_data_in_relation_bag_with_no_auth(harness: Harness) -> None:
    provider_data = ProviderData(
        url="https://path/to/hook",
        body="body",
        method="POST",
        response_ignore=True,
        response_parse=True,
    )

    relation_id = harness.add_relation("kratos-registration-webhook", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.update_relation_data(
        relation_id,
        "provider",
        provider_data.model_dump(exclude_none=True),
    )

    relation_data = harness.charm.kratos_registration_webhook.consume_relation_data(relation_id)

    assert isinstance(harness.charm.events[0], ReadyEvent)
    assert relation_data.auth_enabled is False
    assert relation_data == provider_data


def test_unavailable_event_emitted_when_relation_removed(harness: Harness) -> None:
    relation_id = harness.add_relation("kratos-registration-webhook", "provider")
    harness.add_relation_unit(relation_id, "provider/0")
    harness.remove_relation(relation_id)

    assert any(isinstance(e, UnavailableEvent) for e in harness.charm.events)
