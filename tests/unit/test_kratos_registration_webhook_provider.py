# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

from typing import Any, Generator, List

import pytest
from charms.kratos.v0.kratos_registration_webhook import (
    KratosRegistrationWebhookProvider,
    ProviderData,
    ReadyEvent,
    UnavailableEvent,
)
from ops.charm import CharmBase
from ops.framework import EventBase
from ops.testing import Harness

METADATA = """
name: provider-tester
provides:
  kratos-registration-webhook:
    interface: kratos_registration_webhook
"""

data = ProviderData(
    url="https://path/to/hook",
    body="body",
    method="POST",
    response_ignore=True,
    response_parse=True,
    auth_type="api_key",
    auth_config_name="Authorization",
    auth_config_value="token",
    auth_config_in="header",
)


class KratosRegistrationWebhookProviderCharm(CharmBase):
    def __init__(self, *args: Any, data: ProviderData = data) -> None:
        super().__init__(*args)
        self.kratos_registration_webhook = KratosRegistrationWebhookProvider(self)
        self.events: List = []
        self.data = data

        self.framework.observe(self.kratos_registration_webhook.on.ready, self._on_ready)
        self.framework.observe(self.kratos_registration_webhook.on.unavailable, self._record_event)

    def _on_ready(self, event: EventBase) -> None:
        self.kratos_registration_webhook.update_relations_app_data(self.data)
        self._record_event(event)

    def _record_event(self, event: EventBase) -> None:
        self.events.append(event)


@pytest.fixture()
def harness() -> Generator:
    harness = Harness(KratosRegistrationWebhookProviderCharm, meta=METADATA)
    harness.set_leader(True)
    harness.begin()
    yield harness
    harness.cleanup()


def test_provider_info_in_relation_databag(harness: Harness) -> None:
    relation_id = harness.add_relation("kratos-registration-webhook", "requirer")

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert isinstance(harness.charm.events[0], ReadyEvent)

    secret = relation_data.pop("auth_config_value_secret")
    assert "requirer" in harness.get_secret_grants(secret, relation_id)
    assert (
        harness.model.get_secret(id=secret).get_content()["auth-config-value"]
        == data.auth_config_value
    )

    assert relation_data == {
        "url": data.url,
        "body": data.body,
        "method": data.method,
        "emit_analytics_event": str(data.emit_analytics_event),
        "response_ignore": str(data.response_ignore),
        "response_parse": str(data.response_ignore),
        "auth_type": data.auth_type,
        "auth_config_name": data.auth_config_name,
        "auth_config_in": data.auth_config_in,
    }


def test_provider_info_in_relation_databag_with_no_auth(harness: Harness) -> None:
    harness.charm.data = ProviderData(
        url="https://path/to/hook",
        body="body",
        method="POST",
        response_ignore=True,
        response_parse=True,
    )
    relation_id = harness.add_relation("kratos-registration-webhook", "requirer")

    relation_data = harness.get_relation_data(relation_id, harness.model.app.name)

    assert isinstance(harness.charm.events[0], ReadyEvent)
    assert relation_data == {
        "url": data.url,
        "body": data.body,
        "method": data.method,
        "emit_analytics_event": str(data.emit_analytics_event),
        "response_ignore": str(data.response_ignore),
        "response_parse": str(data.response_ignore),
    }


def test_unavailable_event_emitted_when_relation_removed(harness: Harness) -> None:
    relation_id = harness.add_relation("kratos-registration-webhook", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")
    harness.remove_relation(relation_id)

    assert any(isinstance(e, UnavailableEvent) for e in harness.charm.events)
