#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""A Juju charm for Ory Kratos."""

import logging
from os.path import join
from secrets import token_hex
from typing import Any, Optional

from charms.certificate_transfer_interface.v1.certificate_transfer import (
    CertificatesAvailableEvent,
    CertificatesRemovedEvent,
    CertificateTransferRequires,
)
from charms.data_platform_libs.v0.data_interfaces import (
    DatabaseCreatedEvent,
    DatabaseEndpointsChangedEvent,
    DatabaseRequires,
)
from charms.grafana_k8s.v0.grafana_dashboard import GrafanaDashboardProvider
from charms.hydra.v0.hydra_endpoints import (
    HydraEndpointsRequirer,
)
from charms.identity_platform_login_ui_operator.v0.login_ui_endpoints import (
    LoginUIEndpointsRequirer,
)
from charms.kratos.v0.kratos_info import KratosInfoProvider
from charms.kratos.v0.kratos_registration_webhook import (
    KratosRegistrationWebhookRequirer,
)
from charms.kratos.v0.kratos_registration_webhook import (
    ReadyEvent as KratosRegistrationWebhookReadyEvent,
)
from charms.kratos.v0.kratos_registration_webhook import (
    UnavailableEvent as KratosRegistrationWebhookUnavailableEvent,
)
from charms.kratos_external_idp_integrator.v1.kratos_external_provider import (
    ClientConfigChangedEvent,
    ClientConfigRemovedEvent,
    ExternalIdpRequirer,
    RequirerProviders,
)
from charms.loki_k8s.v1.loki_push_api import LogForwarder
from charms.observability_libs.v0.kubernetes_compute_resources_patch import (
    K8sResourcePatchFailedEvent,
    KubernetesComputeResourcesPatch,
    ResourceRequirements,
    adjust_resource_requirements,
)
from charms.prometheus_k8s.v0.prometheus_scrape import MetricsEndpointProvider
from charms.smtp_integrator.v0.smtp import SmtpDataAvailableEvent, SmtpRequires
from charms.tempo_coordinator_k8s.v0.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
    IngressPerAppRevokedEvent,
)
from lightkube import Client
from ops import EventBase, UpdateStatusEvent, main
from ops.charm import (
    ActionEvent,
    CharmBase,
    ConfigChangedEvent,
    InstallEvent,
    LeaderElectedEvent,
    PebbleReadyEvent,
    RelationBrokenEvent,
    RelationEvent,
    RelationJoinedEvent,
    RemoveEvent,
    UpgradeCharmEvent,
)
from ops.model import (
    ActiveStatus,
    BlockedStatus,
    MaintenanceStatus,
    ModelError,
    SecretNotFoundError,
    WaitingStatus,
)
from ops.pebble import Layer

from cli import CommandLine
from clients import HTTPClient, Identity
from configs import (
    CharmConfig,
    CharmConfigIdentitySchemaProvider,
    ClaimMapper,
    ConfigFile,
    ConfigMapIdentitySchemaProvider,
    DefaultIdentitySchemaProvider,
    IdentitySchema,
    IdentitySchemaConfigMap,
    OIDCProviderConfigMap,
    create_configmaps,
    remove_configmaps,
)
from constants import (
    CERTIFICATE_TRANSFER_INTEGRATION_NAME,
    COOKIE_SECRET_CONTENT_KEY,
    COOKIE_SECRET_LABEL,
    DATABASE_INTEGRATION_NAME,
    EMAIL_TEMPLATE_FILE_PATH,
    GRAFANA_DASHBOARD_INTEGRATION_NAME,
    HYDRA_ENDPOINT_INTEGRATION_NAME,
    INTERNAL_INGRESS_INTEGRATION_NAME,
    KRATOS_ADMIN_PORT,
    KRATOS_EXTERNAL_IDP_INTEGRATOR_INTEGRATION_NAME,
    KRATOS_PUBLIC_PORT,
    LOGGING_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PROMETHEUS_SCRAPE_INTEGRATION_NAME,
    REGISTRATION_WEBHOOK_INTEGRATION_NAME,
    TRACING_INTEGRATION_NAME,
    WORKLOAD_CONTAINER,
)
from exceptions import (
    ClientRequestError,
    IdentityCredentialsNotExistError,
    IdentityNotExistsError,
    IdentitySessionsNotExistError,
    MigrationError,
    PebbleServiceError,
    TooManyIdentitiesError,
)
from integrations import (
    DatabaseConfig,
    ExternalIdpIntegratorData,
    HydraEndpointData,
    InternalIngressData,
    LoginUIEndpointData,
    PeerData,
    PublicIngressData,
    RegistrationWebhookData,
    SmtpData,
    TLSCertificates,
    TracingData,
)
from secret import Secrets
from services import PebbleService, WorkloadService
from utils import (
    container_connectivity,
    database_integration_exists,
    dict_to_action_output,
    external_idp_integrator_integration_exists,
    kratos_info_integration_exists,
    leader_unit,
    peer_integration_exists,
    public_ingress_integration_exists,
)

logger = logging.getLogger(__name__)


class KratosCharm(CharmBase):
    """Charmed Ory Kratos."""

    def __init__(self, *args: Any) -> None:
        super().__init__(*args)

        self.peer_data = PeerData(self.model)
        self.secrets = Secrets(self.model)
        self.charm_config = CharmConfig(self.config)

        self._container = self.unit.get_container(WORKLOAD_CONTAINER)
        self._workload_service = WorkloadService(self.unit)
        self._pebble_service = PebbleService(self.unit)
        self._cli = CommandLine(self._container)

        self._k8s_client = Client(field_manager=self.app.name, namespace=self.model.name)
        self.schemas_configmap = IdentitySchemaConfigMap(
            self._k8s_client, self.model.name, self.app.name
        )
        self.providers_configmap = OIDCProviderConfigMap(
            self._k8s_client, self.model.name, self.app.name
        )

        self.smtp_requirer = SmtpRequires(self)

        self.admin_ingress = IngressPerAppRequirer(
            self,
            relation_name="admin-ingress",
            port=KRATOS_ADMIN_PORT,
            strip_prefix=True,
            redirect_https=False,
        )
        self.public_ingress = IngressPerAppRequirer(
            self,
            relation_name="public-ingress",
            port=KRATOS_PUBLIC_PORT,
            strip_prefix=True,
            redirect_https=False,
        )

        # ingress via raw traefik routing configuration
        self.internal_ingress = TraefikRouteRequirer(
            self,
            self.model.get_relation(INTERNAL_INGRESS_INTEGRATION_NAME),
            INTERNAL_INGRESS_INTEGRATION_NAME,
        )

        self.database_requirer = DatabaseRequires(
            self,
            relation_name=DATABASE_INTEGRATION_NAME,
            database_name=f"{self.model.name}_{self.app.name}",
            extra_user_roles="SUPERUSER",
        )

        self.external_idp_requirer = ExternalIdpRequirer(
            self, relation_name=KRATOS_EXTERNAL_IDP_INTEGRATOR_INTEGRATION_NAME
        )

        self.hydra_endpoints_requirer = HydraEndpointsRequirer(
            self,
            relation_name=HYDRA_ENDPOINT_INTEGRATION_NAME,
        )

        self.registration_webhook_requirer = KratosRegistrationWebhookRequirer(
            self,
            relation_name=REGISTRATION_WEBHOOK_INTEGRATION_NAME,
        )

        self.login_ui_requirer = LoginUIEndpointsRequirer(
            self,
            relation_name=LOGIN_UI_INTEGRATION_NAME,
        )

        self.kratos_info_provider = KratosInfoProvider(self)

        self.metrics_endpoint = MetricsEndpointProvider(
            self,
            relation_name=PROMETHEUS_SCRAPE_INTEGRATION_NAME,
            jobs=[
                {
                    "metrics_path": "/metrics/prometheus",
                    "static_configs": [
                        {
                            "targets": [f"*:{KRATOS_ADMIN_PORT}"],
                        }
                    ],
                }
            ],
        )

        self._log_forwarder = LogForwarder(self, relation_name=LOGGING_INTEGRATION_NAME)
        self.tracing = TracingEndpointRequirer(
            self, relation_name=TRACING_INTEGRATION_NAME, protocols=["otlp_http"]
        )

        self._grafana_dashboards = GrafanaDashboardProvider(
            self, relation_name=GRAFANA_DASHBOARD_INTEGRATION_NAME
        )

        self.certificate_transfer_requirer = CertificateTransferRequires(
            self,
            CERTIFICATE_TRANSFER_INTEGRATION_NAME,
        )

        self.resources_patch = KubernetesComputeResourcesPatch(
            self,
            WORKLOAD_CONTAINER,
            resource_reqs_func=self._resource_reqs_from_config,
        )

        # lifecycle
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.kratos_pebble_ready, self._on_kratos_pebble_ready)
        self.framework.observe(self.on.remove, self._on_remove)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade_charm)
        self.framework.observe(self.on.update_status, self._on_update_status)

        # kratos-info
        self.framework.observe(
            self.kratos_info_provider.on.ready, self._on_kratos_info_provider_ready
        )

        # kratos-registration-webhook
        self.framework.observe(
            self.registration_webhook_requirer.on.ready, self._on_registration_webhook_ready
        )
        self.framework.observe(
            self.registration_webhook_requirer.on.unavailable,
            self._on_registration_webhook_unavailable,
        )

        # hydra-endpoint-info
        self.framework.observe(
            self.on[HYDRA_ENDPOINT_INTEGRATION_NAME].relation_changed, self._on_config_changed
        )

        # ui-endpoint-info
        self.framework.observe(
            self.on[LOGIN_UI_INTEGRATION_NAME].relation_changed, self._on_config_changed
        )

        # pg-database
        self.framework.observe(
            self.database_requirer.on.database_created, self._on_database_created
        )
        self.framework.observe(
            self.database_requirer.on.endpoints_changed, self._on_database_changed
        )
        self.framework.observe(
            self.on[DATABASE_INTEGRATION_NAME].relation_broken, self._on_database_relation_broken
        )

        # admin-ingress
        self.framework.observe(self.admin_ingress.on.ready, self._on_admin_ingress_ready)
        self.framework.observe(self.admin_ingress.on.revoked, self._on_ingress_revoked)

        # public-ingress
        self.framework.observe(self.public_ingress.on.ready, self._on_public_ingress_ready)
        self.framework.observe(self.public_ingress.on.revoked, self._on_ingress_revoked)

        # internal-ingress
        self.framework.observe(
            self.on[INTERNAL_INGRESS_INTEGRATION_NAME].relation_joined,
            self._on_internal_ingress_joined,
        )
        self.framework.observe(
            self.on[INTERNAL_INGRESS_INTEGRATION_NAME].relation_changed,
            self._on_internal_ingress_changed,
        )
        self.framework.observe(
            self.on[INTERNAL_INGRESS_INTEGRATION_NAME].relation_broken,
            self._on_internal_ingress_changed,
        )

        # kratos-external-idp
        self.framework.observe(
            self.external_idp_requirer.on.client_config_changed,
            self._on_external_idp_client_config_changed,
        )
        self.framework.observe(
            self.external_idp_requirer.on.client_config_removed,
            self._on_external_idp_client_config_removed,
        )

        # smtp
        self.framework.observe(
            self.smtp_requirer.on.smtp_data_available, self._on_smtp_data_available
        )

        # receive-ca-cert
        self.framework.observe(
            self.certificate_transfer_requirer.on.certificate_set_updated,
            self._on_certificate_changed,
        )
        self.framework.observe(
            self.certificate_transfer_requirer.on.certificates_removed,
            self._on_certificate_changed,
        )

        # tracing
        self.framework.observe(self.tracing.on.endpoint_changed, self._on_config_changed)
        self.framework.observe(self.tracing.on.endpoint_removed, self._on_config_changed)

        # resource patching
        self.framework.observe(
            self.resources_patch.on.patch_failed, self._on_resource_patch_failed
        )

        # actions
        self.framework.observe(self.on.get_identity_action, self._on_get_identity_action)
        self.framework.observe(self.on.delete_identity_action, self._on_delete_identity_action)
        self.framework.observe(self.on.reset_password_action, self._on_reset_password_action)
        self.framework.observe(
            self.on.list_oidc_accounts_action, self._on_list_oidc_accounts_action
        )
        self.framework.observe(
            self.on.unlink_oidc_account_action, self._on_unlink_oidc_account_action
        )
        self.framework.observe(
            self.on.invalidate_identity_sessions_action,
            self._on_invalidate_identity_sessions_action,
        )
        self.framework.observe(
            self.on.reset_identity_mfa_action,
            self._on_reset_identity_mfa_action,
        )
        self.framework.observe(
            self.on.create_admin_account_action,
            self._on_create_admin_account_action,
        )
        self.framework.observe(self.on.run_migration_action, self._on_run_migration_action)

    @property
    def _pebble_layer(self) -> Layer:
        return self._pebble_service.render_pebble_layer(
            self.charm_config,
            self.secrets,
            DatabaseConfig.load(self.database_requirer),
            TracingData.load(self.tracing),
            HydraEndpointData.load(self.hydra_endpoints_requirer),
            SmtpData.load(self.smtp_requirer),
            PublicIngressData.load(self.public_ingress),
        )

    @property
    def migration_needed(self) -> Optional[bool]:
        if not peer_integration_exists(self):
            return None

        database_config = DatabaseConfig.load(self.database_requirer)
        return self.peer_data[database_config.migration_version] != self._workload_service.version

    def _resource_reqs_from_config(self) -> ResourceRequirements:
        limits = {"cpu": self.model.config.get("cpu"), "memory": self.model.config.get("memory")}
        requests = {"cpu": "100m", "memory": "200Mi"}
        return adjust_resource_requirements(limits, requests, adhere_to_requests=True)

    def _holistic_handler(self, event: EventBase) -> None:
        if not container_connectivity(self):
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        if not peer_integration_exists(self):
            self.unit.status = WaitingStatus("Waiting for peer relation")
            event.defer()
            return

        if not database_integration_exists(self):
            self.unit.status = BlockedStatus("Missing required relation with postgresql")
            return

        if not self.database_requirer.is_resource_created():
            self.unit.status = WaitingStatus("Waiting for database creation")
            return

        if not self.secrets.is_ready:
            self.unit.status = WaitingStatus("Waiting for secret creation")
            return

        if self.migration_needed:
            self.unit.status = WaitingStatus("Waiting for database migration")
            return

        if (
            kratos_info_integration_exists(self)
            or external_idp_integrator_integration_exists(self)
        ) and not public_ingress_integration_exists(self):
            self.unit.status = BlockedStatus(
                "Cannot send integration data without an external hostname. Please "
                "provide an ingress relation."
            )
            return

        if (
            kratos_info_integration_exists(self)
            or external_idp_integrator_integration_exists(self)
        ) and not PublicIngressData.load(self.public_ingress).url:
            self.unit.status = WaitingStatus("Waiting for public ingress")
            event.defer()
            return

        if (
            self.charm_config["enable_oidc_webauthn_sequencing"]
            and self.charm_config["enable_passwordless_login_method"]
        ):
            self.unit.status = BlockedStatus(
                "OIDC-WebAuthn sequencing mode requires `enable_passwordless_login_method=False`. "
                "Please change the config."
            )
            return

        self._update_kratos_external_idp_configurations()

        self._workload_service.push_ca_certs(
            TLSCertificates.load(self.certificate_transfer_requirer).ca_bundle
        )

        if template := self.charm_config["recovery_email_template"]:
            self._container.push(EMAIL_TEMPLATE_FILE_PATH, template, make_dirs=True)

        identity_schema_cm = IdentitySchemaConfigMap(
            self._k8s_client, self.model.name, self.app.name
        )
        identity_schema = IdentitySchema(
            [
                CharmConfigIdentitySchemaProvider(self.charm_config),
                ConfigMapIdentitySchemaProvider(identity_schema_cm),
                DefaultIdentitySchemaProvider(),
            ],
        )

        config_file = ConfigFile.from_sources(
            self.charm_config,
            ClaimMapper(),
            LoginUIEndpointData.load(self.login_ui_requirer),
            PublicIngressData.load(self.public_ingress),
            RegistrationWebhookData.load(self.registration_webhook_requirer),
            ExternalIdpIntegratorData.load(self.external_idp_requirer),
            identity_schema,
            OIDCProviderConfigMap(self._k8s_client, self.model.name, self.app.name),
        )

        try:
            self._pebble_service.plan(self._pebble_layer, config_file)
        except PebbleServiceError as e:
            logger.error(f"Failed to start the service, please check the container logs: {e}")
            self.unit.status = BlockedStatus(
                f"Failed to restart the service, please check the {WORKLOAD_CONTAINER} logs"
            )
            return

        self.unit.status = ActiveStatus()

    def _on_install(self, event: InstallEvent) -> None:
        create_configmaps(
            k8s_client=self._k8s_client,
            namespace=self.model.name,
            app_name=self.app.name,
        )

    def _on_leader_elected(self, event: LeaderElectedEvent) -> None:
        if not self.secrets.is_ready:
            self.secrets[COOKIE_SECRET_LABEL] = {COOKIE_SECRET_CONTENT_KEY: token_hex(16)}

    def _on_config_changed(self, event: ConfigChangedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)
        self._on_kratos_info_provider_ready(event)

    def _on_kratos_pebble_ready(self, event: PebbleReadyEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")

        if not container_connectivity(self):
            event.defer()
            self.unit.status = WaitingStatus("Waiting to connect to Kratos container")
            return

        self._workload_service.open_ports()

        service_version = self._workload_service.version
        self._workload_service.version = service_version

        self._holistic_handler(event)

    def _on_upgrade_charm(self, event: UpgradeCharmEvent) -> None:
        create_configmaps(
            k8s_client=self._k8s_client,
            namespace=self.model.name,
            app_name=self.app.name,
        )

    @leader_unit
    def _on_remove(self, event: RemoveEvent) -> None:
        remove_configmaps(
            k8s_client=self._k8s_client,
            namespace=self.model.name,
            app_name=self.app.name,
        )

    def _on_update_status(self, event: UpdateStatusEvent) -> None:
        self._holistic_handler(event)

    def _on_registration_webhook_ready(self, event: KratosRegistrationWebhookReadyEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)

    def _on_registration_webhook_unavailable(
        self, event: KratosRegistrationWebhookUnavailableEvent
    ) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)

    def _on_resource_patch_failed(self, event: K8sResourcePatchFailedEvent) -> None:
        logger.error(f"Failed to patch resource constraints: {event.message}")
        self.unit.status = BlockedStatus(event.message)

    def _on_kratos_info_provider_ready(self, event: RelationEvent) -> None:
        internal_endpoints = InternalIngressData.load(self.internal_ingress)
        providers_configmap_name = self.providers_configmap.name
        schemas_configmap_name = self.schemas_configmap.name
        configmaps_namespace = self.model.name
        mfa_enabled = self.config.get("enforce_mfa")
        oidc_webauthn_sequencing_enabled = self.config.get("enable_oidc_webauthn_sequencing")

        if not (public_url := PublicIngressData.load(self.public_ingress).url):
            return

        self.kratos_info_provider.send_info_relation_data(
            str(internal_endpoints.admin_endpoint),
            str(internal_endpoints.public_endpoint),
            str(public_url),
            providers_configmap_name,
            schemas_configmap_name,
            configmaps_namespace,
            mfa_enabled,
            oidc_webauthn_sequencing_enabled,
        )

    def _on_database_created(self, event: DatabaseCreatedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")

        if not container_connectivity(self):
            event.defer()
            self.unit.status = WaitingStatus("Container is not connected yet")
            return

        if not peer_integration_exists(self):
            self.unit.status = WaitingStatus(f"Missing integration {PEER_INTEGRATION_NAME}")
            event.defer()
            return

        if not self.secrets.is_ready:
            self.unit.status = WaitingStatus("Waiting for secret creation")
            event.defer()
            return

        if not self.migration_needed:
            self._holistic_handler(event)
            return

        if not self.unit.is_leader():
            logger.info(
                "Unit does not have leadership. Wait for leader unit to run the migration."
            )
            self.unit.status = WaitingStatus("Waiting for leader unit to run the migration")
            event.defer()
            return

        try:
            self._cli.migrate(DatabaseConfig.load(self.database_requirer).dsn)
        except MigrationError:
            self.unit.status = BlockedStatus("Database migration failed")
            logger.error("Auto migration job failed. Please use the run-migration action")
            return

        migration_version = DatabaseConfig.load(self.database_requirer).migration_version
        self.peer_data[migration_version] = self._workload_service.version
        self._holistic_handler(event)

    def _on_database_changed(self, event: DatabaseEndpointsChangedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)

    def _on_database_relation_broken(self, event: RelationBrokenEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self._holistic_handler(event)

    def _on_admin_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's admin ingress URL: %s", event.url)

        self._holistic_handler(event)
        self._on_kratos_info_provider_ready(event)

    def _on_public_ingress_ready(self, event: IngressPerAppReadyEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app's public ingress URL: %s", event.url)

        self._holistic_handler(event)
        self._on_kratos_info_provider_ready(event)

    def _on_ingress_revoked(self, event: IngressPerAppRevokedEvent) -> None:
        if self.unit.is_leader():
            logger.info("This app no longer has ingress")

        self._holistic_handler(event)
        self._on_kratos_info_provider_ready(event)

    @leader_unit
    def _on_internal_ingress_joined(self, event: RelationJoinedEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        self.internal_ingress._relation = event.relation
        self._on_internal_ingress_changed(event)

    @leader_unit
    def _on_internal_ingress_changed(self, event: RelationEvent) -> None:
        self.unit.status = MaintenanceStatus("Configuring resources")
        if self.internal_ingress.is_ready():
            internal_ingress_config = InternalIngressData.load(self.internal_ingress).config
            self.internal_ingress.submit_to_traefik(internal_ingress_config)

    def _update_kratos_external_idp_configurations(self) -> None:
        if not (public_url := PublicIngressData.load(self.public_ingress).url):
            return

        for provider in self.external_idp_requirer.get_providers():
            self.external_idp_requirer.update_registered_provider(
                RequirerProviders.model_validate([
                    {
                        "provider_id": provider.id,
                        "redirect_uri": join(
                            str(public_url),
                            f"self-service/methods/oidc/callback/{provider.id}",
                        ),
                    }
                ]),
                provider.relation_id,
            )

    def _on_external_idp_client_config_changed(self, event: ClientConfigChangedEvent) -> None:
        self._holistic_handler(event)

    def _on_external_idp_client_config_removed(self, event: ClientConfigRemovedEvent) -> None:
        self.unit.status = MaintenanceStatus("Removing external provider")
        self._holistic_handler(event)
        self.external_idp_requirer.remove_registered_provider(int(event.relation_id))

    def _on_smtp_data_available(self, event: SmtpDataAvailableEvent) -> None:
        self._holistic_handler(event)

    def _on_certificate_changed(
        self,
        event: CertificatesAvailableEvent | CertificatesRemovedEvent,
    ) -> None:
        self._holistic_handler(event)

    def _on_get_identity_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = event.params.get("identity-id")
        email = event.params.get("email")
        if identity_id and email:
            event.fail("Provide only one of 'identity-id' or 'email', not both")
            return

        if not identity_id and not email:
            event.fail("You must provide either 'identity-id' or 'email'")
            return

        with HTTPClient(base_url=f"http://127.0.0.1:{KRATOS_ADMIN_PORT}") as client:
            try:
                identity = Identity(client).get(identity_id=identity_id, email=email)
            except IdentityNotExistsError:
                event.fail("Identity not found")
                return
            except TooManyIdentitiesError:
                event.fail(
                    f"Multiple identities found for email '{email}'. Please provide an identity-id instead"
                )
                return
            except ClientRequestError:
                event.fail(f"Failed to fetch the identity for {email or identity_id}.")
                return

        event.log("Successfully fetched the identity.")
        event.set_results(dict_to_action_output(identity))

    def _on_delete_identity_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = event.params.get("identity-id")
        with HTTPClient(base_url=f"http://127.0.0.1:{KRATOS_ADMIN_PORT}") as client:
            try:
                client.delete_identity(identity_id)
            except IdentityNotExistsError:
                event.fail(f"Identity {identity_id} does not exist")
                return
            except ClientRequestError:
                event.fail(f"Failed to delete the identity for {identity_id}")
                return

        event.log(f"Successfully deleted the identity: {identity_id}")
        event.set_results({"id": identity_id})

    def _on_reset_password_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        password = None
        password_secret_id = event.params.get("password-secret-id")
        if password_secret_id:
            try:
                juju_secret = self.model.get_secret(id=password_secret_id)
                password = juju_secret.get_content().get("password")
            except SecretNotFoundError:
                event.fail("Juju secret is not found")
                return
            except ModelError as err:
                event.fail(f"An error occurred when fetching the juju secret: {err}")
                return

        identity_id = event.params.get("identity-id")
        with HTTPClient(base_url=f"http://127.0.0.1:{KRATOS_ADMIN_PORT}") as client:
            try:
                if password:
                    res = Identity(client).reset_password(identity_id, password)
                else:
                    res = client.create_recovery_code(identity_id)
            except IdentityNotExistsError:
                event.fail(f"Identity {identity_id} does not exist")
                return
            except ClientRequestError:
                event.fail("Failed to request Kratos API")
                return

        if password:
            event.log("Password was changed successfully")
        else:
            event.log(
                "Recovery code created successfully. Use the returned link to reset the identity's password"
            )

        event.set_results(dict_to_action_output(res))

    def _on_list_oidc_accounts_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = event.params.get("identity-id")
        with HTTPClient(base_url=f"http://127.0.0.1:{KRATOS_ADMIN_PORT}") as client:
            try:
                oidc_identifiers = Identity(client).get_oidc_identifiers(identity_id=identity_id)
            except IdentityNotExistsError:
                event.fail(f"Identity {identity_id} does not exist")
                return
            except ClientRequestError:
                event.fail(f"Failed to fetch the identity OIDC credentials for {identity_id}")
                return

        if not oidc_identifiers:
            event.log("Identity OIDC credentials not found")
            return

        event.log("Successfully fetched the identity OIDC credentials")
        event.set_results({"identifiers": "\n".join(oidc_identifiers)})

    def _on_unlink_oidc_account_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = event.params.get("identity-id")
        credential_id = event.params.get("credential-id")
        with HTTPClient(base_url=f"http://127.0.0.1:{KRATOS_ADMIN_PORT}") as client:
            try:
                client.delete_mfa_credential(
                    identity_id, mfa_type="oidc", params={"identifier": credential_id}
                )
            except IdentityCredentialsNotExistError:
                event.log(f"Identity {identity_id} has no oidc credentials")
                return
            except ClientRequestError:
                event.fail("Failed to delete the oidc credentials")
                return

        event.log(f"Successfully unlink the oidc account for identity {identity_id}")

    def _on_invalidate_identity_sessions_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = event.params.get("identity-id")
        with HTTPClient(base_url=f"http://127.0.0.1:{KRATOS_ADMIN_PORT}") as client:
            try:
                client.invalidate_sessions(identity_id)
            except IdentitySessionsNotExistError:
                event.log(f"Identity {identity_id} has no sessions")
                return
            except ClientRequestError:
                event.fail(f"Failed to invalidate and delete sessions for identity {identity_id}")
                return

        event.log("Successfully invalidated and deleted the sessions")

    def _on_reset_identity_mfa_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        identity_id = event.params.get("identity-id")
        mfa_type = event.params.get("mfa-type")
        with HTTPClient(base_url=f"http://127.0.0.1:{KRATOS_ADMIN_PORT}") as client:
            try:
                client.delete_mfa_credential(identity_id, mfa_type)
            except IdentityCredentialsNotExistError:
                event.log(f"Identity {identity_id} has no {mfa_type} credentials")
                return
            except ClientRequestError:
                event.fail(f"Failed to reset the {mfa_type} credentials")
                return

        event.log(f"Successfully reset the {mfa_type} credentials for identity {identity_id}")

    def _on_create_admin_account_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        traits = {
            "username": event.params.get("username"),
            "email": event.params.get("email"),
            "name": event.params.get("name"),
            "phone_number": event.params.get("phone-number"),
        }
        traits = {k: v for k, v in traits.items() if v is not None}

        password = None
        password_secret_id = event.params.get("password-secret-id")
        if password_secret_id:
            try:
                juju_secret = self.model.get_secret(id=password_secret_id)
                password = juju_secret.get_content().get("password")
            except SecretNotFoundError:
                event.fail("Juju secret is not found")
                return
            except ModelError as err:
                event.fail(f"An error occurred when fetching the juju secret: {err}")
                return

        with HTTPClient(base_url=f"http://127.0.0.1:{KRATOS_ADMIN_PORT}") as client:
            try:
                identity = client.create_identity(traits, schema_id="admin_v0", password=password)
            except ClientRequestError:
                event.fail("Failed to create the admin account")
                return

            identity_id = identity["id"]
            event.log(f"Successfully created the admin account: {identity_id}")
            res = {"identity-id": identity_id}
            if not password:
                try:
                    recovery = client.create_recovery_code(identity_id)
                except ClientRequestError:
                    event.fail("Failed to create recovery code for the admin account")
                    return

                res.update(recovery)

        event.set_results(dict_to_action_output(res))

    def _on_run_migration_action(self, event: ActionEvent) -> None:
        if not self._workload_service.is_running:
            event.fail("Service is not ready. Please re-run the action when the charm is active")
            return

        if not peer_integration_exists(self):
            event.fail("Peer integration is not ready")
            return

        event.log("Start migrating the database")

        timeout = float(event.params.get("timeout", 120))
        try:
            self._cli.migrate(
                dsn=DatabaseConfig.load(self.database_requirer).dsn,
                timeout=timeout,
            )
        except MigrationError as err:
            event.fail(f"Database migration failed: {err}")
            return
        else:
            event.log("Successfully migrated the database")

        migration_version = DatabaseConfig.load(self.database_requirer).migration_version
        self.peer_data[migration_version] = self._workload_service.version
        event.log("Successfully updated migration version")


if __name__ == "__main__":
    main(KratosCharm)
