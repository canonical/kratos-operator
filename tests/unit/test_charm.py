# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import json
from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from ops import testing
from scenario import TCPPort

from charm import KratosCharm
from constants import (
    KRATOS_ADMIN_PORT,
    KRATOS_PUBLIC_PORT,
    PEER_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)


class TestStartEvent:
    def test_when_event_emitted(self, mocked_create_configmaps: MagicMock) -> None:
        ctx = testing.Context(KratosCharm)
        state_in = testing.State()

        ctx.run(ctx.on.install(), state_in)

        mocked_create_configmaps.assert_called_once()


class TestLeaderElectedEvent:
    @pytest.fixture
    def mocked_secret(self) -> MagicMock:
        return MagicMock()

    @patch("charm.Secrets", autospec=True)
    def test_when_secrets_ready(
        self, mocked_secret_cls: MagicMock, mocked_secret: MagicMock
    ) -> None:
        mocked_secret.is_ready = True
        mocked_secret_cls.return_value = mocked_secret

        ctx = testing.Context(KratosCharm)
        state_in = testing.State(leader=True)

        ctx.run(ctx.on.leader_elected(), state_in)

        mocked_secret.__setitem__.assert_not_called()

    @patch("charm.Secrets", autospec=True)
    def test_when_event_emitted(
        self, mocked_secret_cls: MagicMock, mocked_secret: MagicMock
    ) -> None:
        mocked_secret.is_ready = False
        mocked_secret_cls.return_value = mocked_secret

        ctx = testing.Context(KratosCharm)
        state_in = testing.State(leader=True)

        ctx.run(ctx.on.leader_elected(), state_in)

        mocked_secret.__setitem__.assert_called_once()


class TestConfigChangeEvent:
    def test_when_event_emitted(
        self,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        state_in = testing.State()

        ctx.run(ctx.on.config_changed(), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestPebbleReadyEvent:
    def test_when_container_not_connected(
        self,
        mocked_workload_service: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(containers={container})

        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert isinstance(state_out.unit_status, testing.WaitingStatus)
        mocked_workload_service.open_ports.assert_not_called()
        mocked_charm_holistic_handler.assert_not_called()

    def test_when_event_emitted(
        self,
        mocked_workload_service_version: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container})

        state_out = ctx.run(ctx.on.pebble_ready(container), state_in)

        assert state_out.opened_ports == {
            TCPPort(port=KRATOS_PUBLIC_PORT, protocol="tcp"),
            TCPPort(port=KRATOS_ADMIN_PORT, protocol="tcp"),
        }
        mocked_charm_holistic_handler.assert_called_once()
        assert mocked_workload_service_version.call_count > 1, (
            "workload service version should be set"
        )
        assert mocked_workload_service_version.call_args[0] == (
            mocked_workload_service_version.return_value,
        )


class TestRemoveEvent:
    def test_when_not_leader_unit(self, mocked_remove_configmaps: MagicMock) -> None:
        ctx = testing.Context(KratosCharm)
        state_in = testing.State(leader=False)

        ctx.run(ctx.on.remove(), state_in)

        mocked_remove_configmaps.assert_not_called()

    def test_when_event_emitted(self, mocked_remove_configmaps: MagicMock) -> None:
        ctx = testing.Context(KratosCharm)
        state_in = testing.State(leader=True)

        ctx.run(ctx.on.remove(), state_in)

        mocked_remove_configmaps.assert_called_once()


class TestUpgradeCharmEvent:
    def test_when_event_emitted(self, mocked_create_configmaps: MagicMock) -> None:
        ctx = testing.Context(KratosCharm)

        ctx.run(ctx.on.upgrade_charm(), testing.State())

        mocked_create_configmaps.assert_called_once()


class TestUpdateStatusEvent:
    def test_when_event_emitted(self, mocked_charm_holistic_handler: MagicMock) -> None:
        ctx = testing.Context(KratosCharm)

        ctx.run(ctx.on.update_status(), testing.State())

        mocked_charm_holistic_handler.assert_called_once()


class TestDatabaseCreatedEvent:
    def test_when_container_not_connected(
        self,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        charm_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=False)
        state_in = testing.State(
            containers={container},
            relations=[database_integration, peer_integration],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus("Container is not connected yet")

    def test_when_peer_integration_not_exists(
        self,
        database_integration: testing.Relation,
        charm_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[database_integration],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus(
            f"Missing integration {PEER_INTEGRATION_NAME}"
        )

    @patch("charm.CommandLine.migrate")
    def test_when_migration_not_needed(
        self,
        mocked_cli_migrate: MagicMock,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        charm_secret: testing.Secret,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[database_integration, peer_integration],
            secrets=[charm_secret],
            leader=True,
        )

        with patch(
            "charm.KratosCharm.migration_needed",
            new_callable=PropertyMock,
            return_value=False,
        ):
            ctx.run(ctx.on.relation_changed(database_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()
        mocked_cli_migrate.assert_not_called()

    def test_when_not_leader_unit(
        self,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        charm_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[database_integration, peer_integration],
            secrets=[charm_secret],
            leader=False,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        assert state_out.unit_status == testing.WaitingStatus(
            "Waiting for leader unit to run the migration"
        )

    @patch("charm.CommandLine.migrate")
    def test_when_leader_unit(
        self,
        mocked_cli_migrate: MagicMock,
        database_integration: testing.Relation,
        peer_integration: testing.PeerRelation,
        charm_secret: testing.Secret,
        mocked_migration_needed: MagicMock,
        mocked_charm_holistic_handler: MagicMock,
        mocked_workload_service_version: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[database_integration, peer_integration],
            secrets=[charm_secret],
            leader=True,
        )

        state_out = ctx.run(ctx.on.relation_changed(database_integration), state_in)

        mocked_cli_migrate.assert_called_once()
        mocked_charm_holistic_handler.assert_called_once()

        assert state_out.get_relations(PEER_INTEGRATION_NAME)[0].local_app_data[
            f"migration_version_{database_integration.id}"
        ] == json.dumps(mocked_workload_service_version.return_value)


class TestDatabaseIntegrationBrokenEvent:
    def test_when_event_emitted(
        self,
        database_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(containers={container}, relations=[database_integration])

        ctx.run(ctx.on.relation_broken(database_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestRegistrationWebhookReadyEvent:
    def test_when_event_emitted(
        self,
        registration_webhook_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container}, relations=[registration_webhook_integration]
        )

        ctx.run(ctx.on.relation_changed(registration_webhook_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestRegistrationWebhookUnavailableEvent:
    def test_when_event_emitted(
        self,
        registration_webhook_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container}, relations=[registration_webhook_integration]
        )

        ctx.run(ctx.on.relation_broken(registration_webhook_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestPublicIngressReadyEvent:
    def test_when_event_emitted(
        self,
        public_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[public_ingress_integration],
        )

        ctx.run(ctx.on.relation_joined(public_ingress_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestPublicIngressRevokedEvent:
    def test_when_event_emitted(
        self,
        public_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[public_ingress_integration],
        )

        ctx.run(ctx.on.relation_broken(public_ingress_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestAdminIngressReadyEvent:
    def test_when_event_emitted(
        self,
        admin_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[admin_ingress_integration],
        )

        ctx.run(ctx.on.relation_joined(admin_ingress_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestAdminIngressRevokedEvent:
    def test_when_event_emitted(
        self,
        admin_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[admin_ingress_integration],
        )

        ctx.run(ctx.on.relation_broken(admin_ingress_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestInternalIngressRelationJoinedEvent:
    @patch("charm.TraefikRouteRequirer.submit_to_traefik")
    def test_when_not_leader_unit(
        self,
        mocked_submit_to_traefik: MagicMock,
        internal_ingress_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[internal_ingress_integration],
            leader=False,
        )

        ctx.run(ctx.on.relation_joined(internal_ingress_integration), state_in)

        mocked_submit_to_traefik.assert_not_called()

    @patch("charm.TraefikRouteRequirer.submit_to_traefik")
    def test_when_event_emitted(
        self,
        mocked_submit_to_traefik: MagicMock,
        internal_ingress_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[internal_ingress_integration],
            leader=True,
        )

        ctx.run(ctx.on.relation_joined(internal_ingress_integration), state_in)

        mocked_submit_to_traefik.assert_called_once()


class TestInternalIngressRelationChangedEvent:
    @patch("charm.TraefikRouteRequirer.submit_to_traefik")
    def test_when_not_leader_unit(
        self,
        mocked_submit_to_traefik: MagicMock,
        internal_ingress_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[internal_ingress_integration],
            leader=False,
        )

        ctx.run(ctx.on.relation_changed(internal_ingress_integration), state_in)

        mocked_submit_to_traefik.assert_not_called()

    @patch("charm.TraefikRouteRequirer.submit_to_traefik")
    def test_when_event_emitted(
        self,
        mocked_submit_to_traefik: MagicMock,
        internal_ingress_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[internal_ingress_integration],
            leader=True,
        )

        ctx.run(ctx.on.relation_changed(internal_ingress_integration), state_in)

        mocked_submit_to_traefik.assert_called_once()


class TestInternalIngressRelationBrokenEvent:
    @patch("charm.TraefikRouteRequirer.submit_to_traefik")
    def test_when_not_leader_unit(
        self,
        mocked_submit_to_traefik: MagicMock,
        internal_ingress_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[internal_ingress_integration],
            leader=False,
        )

        ctx.run(ctx.on.relation_broken(internal_ingress_integration), state_in)

        mocked_submit_to_traefik.assert_not_called()

    @patch("charm.TraefikRouteRequirer.submit_to_traefik")
    def test_when_event_emitted(
        self,
        mocked_submit_to_traefik: MagicMock,
        internal_ingress_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[internal_ingress_integration],
            leader=True,
        )

        ctx.run(ctx.on.relation_broken(internal_ingress_integration), state_in)

        mocked_submit_to_traefik.assert_not_called()


class TestExternalIdpClientConfigChangedEvent:
    def test_when_event_emitted(
        self,
        external_idp_integrator_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[external_idp_integrator_integration],
        )

        ctx.run(ctx.on.relation_changed(external_idp_integrator_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestExternalIdpClientConfigRemovedEvent:
    @patch("charm.ExternalIdpRequirer.remove_registered_provider")
    def test_when_event_emitted(
        self,
        mocked_remove_registered_provider: MagicMock,
        external_idp_integrator_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[external_idp_integrator_integration],
        )

        ctx.run(ctx.on.relation_broken(external_idp_integrator_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()
        mocked_remove_registered_provider.assert_called_once()


class TestSmtpDataAvailableEvent:
    def test_when_event_emitted(
        self,
        smtp_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[smtp_integration],
        )

        ctx.run(ctx.on.relation_changed(smtp_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestCertificateSetUpdatedEvent:
    def test_when_event_emitted(
        self,
        certificate_transfer_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[certificate_transfer_integration],
        )

        ctx.run(ctx.on.relation_changed(certificate_transfer_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestCertificatesRemovedEvent:
    def test_when_event_emitted(
        self,
        certificate_transfer_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[certificate_transfer_integration],
        )

        ctx.run(ctx.on.relation_broken(certificate_transfer_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestKratosInfoReadyEvent:
    @patch("charm.KratosInfoProvider.send_info_relation_data")
    def test_when_event_emitted(
        self,
        mocked_send_info_relation_data: MagicMock,
        kratos_info_integration: testing.Relation,
        public_ingress_integration: testing.Relation,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[kratos_info_integration, public_ingress_integration],
        )

        ctx.run(ctx.on.relation_created(kratos_info_integration), state_in)

        mocked_send_info_relation_data.assert_called_once()


class TestHydraEndpointInfoRelationChangedEvent:
    def test_when_event_emitted(
        self,
        hydra_endpoint_info_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[hydra_endpoint_info_integration],
        )

        ctx.run(ctx.on.relation_changed(hydra_endpoint_info_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestTracingEndpointChangedEvent:
    def test_when_event_emitted(
        self,
        tracing_integration: testing.Relation,
        public_ingress_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[tracing_integration],
        )

        ctx.run(ctx.on.relation_changed(tracing_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()


class TestTracingEndpointRemovedEvent:
    def test_when_event_emitted(
        self,
        tracing_integration: testing.Relation,
        mocked_charm_holistic_handler: MagicMock,
    ) -> None:
        ctx = testing.Context(KratosCharm)
        container = testing.Container(WORKLOAD_CONTAINER, can_connect=True)
        state_in = testing.State(
            containers={container},
            relations=[tracing_integration],
        )

        ctx.run(ctx.on.relation_broken(tracing_integration), state_in)

        mocked_charm_holistic_handler.assert_called_once()
