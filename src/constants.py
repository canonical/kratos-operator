# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""File containing all constants."""

from pathlib import Path

# Charm constants
WORKLOAD_CONTAINER_NAME = "kratos"
EMAIL_TEMPLATE_FILE_PATH = Path("/etc/config/templates") / "recovery-body.html.gotmpl"
MAPPERS_LOCAL_DIR_PATH = Path("claim_mappers")

# Application constants
KRATOS_ADMIN_PORT = 4434
KRATOS_PUBLIC_PORT = 4433
KRATOS_SERVICE_COMMAND = "kratos serve all"
DEFAULT_SCHEMA_ID_FILE_NAME = "default.schema"
KRATOS_CONFIG_MAP_NAME = "kratos-config"
LOG_LEVELS = ["panic", "fatal", "error", "warn", "info", "debug", "trace"]
CONFIG_DIR_PATH = Path("/etc/config/kratos")
CONFIG_FILE_PATH = CONFIG_DIR_PATH / "kratos.yaml"
IDENTITY_SCHEMAS_LOCAL_DIR_PATH = Path("identity_schemas")
PROVIDERS_CONFIGMAP_FILE_NAME = "idps.yaml"

# Integration constants
PEER_RELATION_NAME = "kratos-peers"
INTERNAL_INGRESS_RELATION_NAME = "internal-ingress"
CERTIFICATE_TRANSFER_RELATION_NAME = "receive-ca-cert"
DB_RELATION_NAME = "pg-database"
HYDRA_RELATION_NAME = "hydra-endpoint-info"
LOGIN_UI_RELATION_NAME = "ui-endpoint-info"
KRATOS_INFO_RELATION_NAME = "kratos-info"
PROMETHEUS_SCRAPE_RELATION_NAME = "metrics-endpoint"
LOKI_PUSH_API_RELATION_NAME = "logging"
GRAFANA_DASHBOARD_RELATION_NAME = "grafana-dashboard"
TRACING_RELATION_NAME = "tracing"

# Peer data keys
PEER_KEY_DB_MIGRATE_VERSION = "db_migrate_version"

# Secret constants
SECRET_LABEL = "cookie_secret"
COOKIE_SECRET_KEY = "cookiesecret"

# Cert transfer constants
LOCAL_CA_CERTS_PATH = Path("/usr/local/share/ca-certificates")
CA_BUNDLE_PATH = "/etc/ssl/certs/ca-certificates.crt"
