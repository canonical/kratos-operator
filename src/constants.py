# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path, PurePath
from string import Template

# Charm constants
POSTGRESQL_DSN_TEMPLATE = Template("postgres://$username:$password@$endpoint/$database")
WORKLOAD_SERVICE = "kratos"
WORKLOAD_CONTAINER = "kratos"
PEBBLE_READY_CHECK_NAME = "ready"
EMAIL_TEMPLATE_FILE_PATH = Path("/etc/config/templates") / "recovery-body.html.gotmpl"
MAPPERS_LOCAL_DIR_PATH = Path("claim_mappers")

# Application constants
KRATOS_ADMIN_PORT = 4434
KRATOS_PUBLIC_PORT = 4433
DEFAULT_SCHEMA_ID_FILE_NAME = "default.schema"
CONFIG_DIR_PATH = PurePath("/etc/config/kratos")
CONFIG_FILE_PATH = CONFIG_DIR_PATH / "kratos.yaml"
IDENTITY_SCHEMAS_LOCAL_DIR_PATH = Path("identity_schemas")
PROVIDERS_CONFIGMAP_FILE_NAME = "idps.json"
CA_BUNDLE_PATH = Path("/etc/ssl/certs/ca-certificates.crt")
INTEGRATION_CA_BUNDLE_PATH = Path("/usr/local/share/ca-certificates/ca-certificates.crt")

# Integration constants
PEER_INTEGRATION_NAME = "kratos-peers"
INTERNAL_ROUTE_INTEGRATION_NAME = "internal-route"
CERTIFICATE_TRANSFER_INTEGRATION_NAME = "receive-ca-cert"
DATABASE_INTEGRATION_NAME = "pg-database"
HYDRA_ENDPOINT_INTEGRATION_NAME = "hydra-endpoint-info"
KRATOS_EXTERNAL_IDP_INTEGRATOR_INTEGRATION_NAME = "kratos-external-idp"
REGISTRATION_WEBHOOK_INTEGRATION_NAME = "kratos-registration-webhook"
LOGIN_UI_INTEGRATION_NAME = "ui-endpoint-info"
KRATOS_INFO_INTEGRATION_NAME = "kratos-info"
PROMETHEUS_SCRAPE_INTEGRATION_NAME = "metrics-endpoint"
LOGGING_INTEGRATION_NAME = "logging"
GRAFANA_DASHBOARD_INTEGRATION_NAME = "grafana-dashboard"
TRACING_INTEGRATION_NAME = "tracing"
PUBLIC_ROUTE_INTEGRATION_NAME = "public-route"

# Action constants
ALLOWED_MFA_CREDENTIAL_TYPES = ("totp", "lookup_secret", "webauthn")

# Secret constants
COOKIE_SECRET_LABEL = "cookie_secret"
COOKIE_SECRET_CONTENT_KEY = "cookiesecret"
SECRET_ID_KEY = "secret-id"
