# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import json
from pathlib import Path
from typing import Any, Dict, Tuple
from unittest.mock import MagicMock, Mock

import pytest
import requests
import yaml
from capture_events import capture_events
from charms.kratos.v0.kratos_info import KratosInfoRelationReadyEvent
from ops.model import ActiveStatus, BlockedStatus, Container, WaitingStatus
from ops.pebble import ExecError, TimeoutError
from ops.testing import Harness

from constants import INTERNAL_INGRESS_RELATION_NAME

CONFIG_DIR = Path("/etc/config")
CONTAINER_NAME = "kratos"
ADMIN_PORT = "4434"
DB_USERNAME = "fake_relation_id_1"
DB_PASSWORD = "fake-password"
DB_ENDPOINTS = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"
DEFAULT_BROWSER_RETURN_URL = "http://example-default-return-url.com"
IDENTITY_SCHEMA = {
    "$id": "https://schemas.ory.sh/presets/kratos/quickstart/email-password/identity.schema.json",
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "Person",
    "type": "object",
    "properties": {
        "traits": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "format": "email", "title": "E-Mail"},
                "name": {"type": "string"},
            },
        }
    },
}
PROJ_ROOT_DIR = Path(__file__).parents[2]


def setup_postgres_relation(harness: Harness) -> None:
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")
    harness.update_relation_data(
        db_relation_id,
        "postgresql-k8s",
        {
            "data": '{"database": "database", "extra-user-roles": "SUPERUSER"}',
            "database": "kratos-model_kratos",
            "endpoints": DB_ENDPOINTS,
            "password": DB_PASSWORD,
            "username": DB_USERNAME,
        },
    )


def setup_ingress_relation(harness: Harness, type: str) -> int:
    relation_id = harness.add_relation(f"{type}-ingress", f"{type}-traefik")
    harness.add_relation_unit(relation_id, f"{type}-traefik/0")
    harness.update_relation_data(
        relation_id,
        f"{type}-traefik",
        {"ingress": json.dumps({"url": f"http://{type}:80/{harness.model.name}-kratos"})},
    )
    return relation_id


def setup_internal_ingress_relation(harness: Harness, type: str) -> int:
    relation_id = harness.add_relation(
        f"{INTERNAL_INGRESS_RELATION_NAME}",
        f"{type}-traefik",
    )
    harness.add_relation_unit(
        relation_id,
        f"{type}-traefik/0",
    )
    harness.update_relation_data(
        relation_id,
        f"{type}-traefik",
        {"external_host": "test.staging.canonical.com", "scheme": "https"},
    )

    return relation_id


def setup_peer_relation(harness: Harness) -> None:
    rel_id = harness.add_relation("kratos-peers", "kratos")
    harness.add_relation_unit(rel_id, "kratos/1")


def setup_hydra_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("hydra-endpoint-info", "hydra")
    harness.add_relation_unit(relation_id, "hydra/0")
    harness.update_relation_data(
        relation_id,
        "hydra",
        {
            "admin_endpoint": "http://hydra-admin-url:80/testing-hydra",
            "public_endpoint": "http://hydra-public-url:80/testing-hydra",
        },
    )
    return relation_id


def setup_login_ui_relation(harness: Harness) -> tuple[int, dict]:
    relation_id = harness.add_relation("ui-endpoint-info", "identity-platform-login-ui-operator")
    harness.add_relation_unit(relation_id, "identity-platform-login-ui-operator/0")
    endpoint = f"https://public/{harness.model.name}-identity-platform-login-ui-operator"
    databag = {
        "consent_url": f"{endpoint}/ui/consent",
        "error_url": f"{endpoint}/ui/error",
        "login_url": f"{endpoint}/ui/login",
        "oidc_error_url": f"{endpoint}/ui/oidc_error",
        "device_verification_url": f"{endpoint}/ui/device_code",
        "post_device_done_url": f"{endpoint}/ui/device_complete",
        "settings_url": f"{endpoint}/ui/settings",
        "webauthn_settings_url": f"{endpoint}/ui/setup_passkey",
        "recovery_url": f"{endpoint}/ui/recovery",
    }
    harness.update_relation_data(
        relation_id,
        "identity-platform-login-ui-operator",
        databag,
    )
    return (relation_id, databag)


def setup_loki_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("logging", "loki-k8s")
    harness.add_relation_unit(relation_id, "loki-k8s/0")
    databag = {
        "promtail_binary_zip_url": json.dumps({
            "amd64": {
                "filename": "promtail-static-amd64",
                "zipsha": "543e333b0184e14015a42c3c9e9e66d2464aaa66eca48b29e185a6a18f67ab6d",
                "binsha": "17e2e271e65f793a9fbe81eab887b941e9d680abe82d5a0602888c50f5e0cac9",
                "url": "https://github.com/canonical/loki-k8s-operator/releases/download/promtail-v2.5.0/promtail-static-amd64.gz",
            }
        }),
    }
    unit_databag = {
        "endpoint": json.dumps({
            "url": "http://loki-k8s-0.loki-k8s-endpoints.model0.svc.cluster.local:3100/loki/api/v1/push"
        })
    }
    harness.update_relation_data(
        relation_id,
        "loki-k8s/0",
        unit_databag,
    )
    harness.update_relation_data(
        relation_id,
        "loki-k8s",
        databag,
    )
    return relation_id


def setup_tempo_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("tracing", "tempo-k8s")
    harness.add_relation_unit(relation_id, "tempo-k8s/0")
    trace_databag = {
        "receivers": '[{"protocol": {"name": "otlp_http", "type":"http"},"url":"http://tempo-k8s-0.tempo-k8s-endpoints.namespace.svc.cluster.local:4318"}]',
    }
    harness.update_relation_data(
        relation_id,
        "tempo-k8s",
        trace_databag,
    )
    return relation_id


def setup_smtp_relation(harness: Harness, transport_security: str, skip_ssl_verify: str) -> int:
    secret_content = {"password": "some-password"}
    secret_id = harness.add_user_secret(secret_content)
    harness.grant_secret(secret_id, "kratos")

    smtp_relation_id = harness.add_relation("smtp", "smtp-provider")
    harness.add_relation_unit(smtp_relation_id, "smtp-provider/0")
    harness.update_relation_data(
        smtp_relation_id,
        "smtp-provider",
        {
            "host": "example.smtp",
            "port": "25",
            "user": "example_user",
            "password_id": secret_id,
            "auth_type": "plain",
            "transport_security": transport_security,
            "domain": "domain",
            "skip_ssl_verify": skip_ssl_verify,
        },
    )
    return smtp_relation_id


def setup_kratos_info_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("kratos-info", "requirer")
    harness.add_relation_unit(relation_id, "requirer/0")

    return relation_id


def trigger_database_changed(harness: Harness) -> None:
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")
    harness.update_relation_data(
        db_relation_id,
        "postgresql-k8s",
        {
            "data": '{"database": "database", "extra-user-roles": "SUPERUSER"}',
            "endpoints": DB_ENDPOINTS,
        },
    )


def setup_external_provider_relation(harness: Harness) -> tuple[int, dict]:
    data = {
        "client_id": "client_id",
        "provider": "generic",
        "label": "generic",
        "secret_backend": "relation",
        "client_secret": "client_secret",
        "issuer_url": "https://example.com/oidc",
        "provider_id": "Provider",
        "scope": "profile email",
    }
    relation_id = harness.add_relation("kratos-external-idp", "kratos-external-idp-integrator")
    harness.add_relation_unit(relation_id, "kratos-external-idp-integrator/0")
    harness.update_relation_data(
        relation_id,
        "kratos-external-idp-integrator",
        {
            "providers": json.dumps([data]),
        },
    )
    return relation_id, data


def validate_config(
    expected_config: Dict[str, Any],
    config: Dict[str, Any],
    validate_schemas: bool = True,
    validate_mappers: bool = True,
) -> None:
    secrets = config.pop("secrets", None)
    if secrets:
        assert "cookie" in secrets
        assert len(secrets["cookie"]) > 0

    expected_schemas = expected_config["identity"].pop("schemas")
    schemas = config["identity"].pop("schemas")
    assert len(expected_schemas) == len(schemas)
    if validate_schemas:
        assert all(schema in schemas for schema in expected_schemas)

    if not validate_mappers and "methods" in config["selfservice"]:
        if "oidc" in config["selfservice"]["methods"]:
            for p in config["selfservice"]["methods"]["oidc"]["config"]["providers"]:
                p.pop("mapper_url")
    if not validate_mappers and "methods" in config["selfservice"]:
        if "oidc" in config["selfservice"]["methods"]:
            for p in expected_config["selfservice"]["methods"]["oidc"]["config"]["providers"]:
                p.pop("mapper_url")

    assert config == expected_config


def test_on_pebble_ready_cannot_connect_container(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, WaitingStatus)


def test_on_pebble_ready_correct_plan(
    harness: Harness, mocked_migration_is_needed: MagicMock, mocked_get_secret: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_plan = {
        "checks": {
            "kratos-alive": {
                "http": {"url": f"http://localhost:{ADMIN_PORT}/admin/health/alive"},
                "override": "replace",
            },
            "kratos-ready": {
                "http": {"url": f"http://localhost:{ADMIN_PORT}/admin/health/ready"},
                "override": "replace",
            },
        },
        "services": {
            CONTAINER_NAME: {
                "override": "replace",
                "summary": "Kratos Operator layer",
                "startup": "disabled",
                "command": "kratos serve all --config /etc/config/kratos/kratos.yaml",
            }
        },
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    environment = updated_plan["services"][CONTAINER_NAME].pop("environment")
    assert expected_plan == updated_plan
    assert (
        environment["DSN"]
        == f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/{harness.model.name}_{harness.charm.app.name}"
    )
    assert environment["SERVE_PUBLIC_BASE_URL"] is None


def test_on_pebble_ready_correct_plan_with_dev_flag(
    harness: Harness,
    mocked_migration_is_needed: MagicMock,
    mocked_get_secret: MagicMock,
    caplog: pytest.LogCaptureFixture,
) -> None:
    harness.update_config({"dev": True})
    container = harness.model.unit.get_container(CONTAINER_NAME)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_plan = {
        "checks": {
            "kratos-alive": {
                "http": {"url": "http://localhost:4434/admin/health/alive"},
                "override": "replace",
            },
            "kratos-ready": {
                "http": {"url": "http://localhost:4434/admin/health/ready"},
                "override": "replace",
            },
        },
        "services": {
            CONTAINER_NAME: {
                "override": "replace",
                "summary": "Kratos Operator layer",
                "startup": "disabled",
                "command": "kratos serve all --config /etc/config/kratos/kratos.yaml --dev",
            }
        },
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    updated_plan["services"][CONTAINER_NAME].pop("environment")
    assert expected_plan == updated_plan
    assert "Running Kratos in dev mode, don't do this in production" in caplog.messages


def test_on_pebble_ready_service_does_not_exist_when_database_not_created(
    harness: Harness,
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert "kratos" not in harness.model.unit.get_container("kratos").get_services()


def test_on_pebble_ready_service_started_when_database_is_created(
    harness: Harness, mocked_migration_is_needed: MagicMock, mocked_get_secret: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    harness.charm.on.kratos_pebble_ready.emit(container)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert harness.model.unit.status == ActiveStatus()


def test_on_pebble_ready_has_correct_config_when_database_is_created(
    harness: Harness, lk_client: MagicMock
) -> None:
    setup_postgres_relation(harness)
    _, login_databag = setup_login_ui_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
                "totp": {
                    "enabled": True,
                    "config": {
                        "issuer": "Identity Platform",
                    },
                },
                "lookup_secret": {
                    "enabled": True,
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    validate_config(
        expected_config,
        yaml.safe_load(harness.charm._render_conf_file()),
        validate_schemas=False,
        validate_mappers=False,
    )


def test_on_pebble_ready_when_missing_database_relation(harness: Harness) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, BlockedStatus)
    assert "Missing required relation with postgresql" in harness.charm.unit.status.message


def test_on_pebble_ready_when_database_not_created_yet(harness: Harness) -> None:
    trigger_database_changed(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, WaitingStatus)
    assert "Waiting for database creation" in harness.charm.unit.status.message


def test_on_pebble_ready_lk_called(
    harness: Harness,
    lk_client: MagicMock,
    mocked_get_secret: MagicMock,
    mocked_run_migration: MagicMock,
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    lk_client.patch.assert_called_once()


@pytest.mark.parametrize(
    "transport_security,method,skip_ssl_verify,additional_param",
    [
        ("tls", "smtps", "False", ""),
        ("starttls", "smtp", "False", ""),
        ("tls", "smtps", "True", "?skip_ssl_verify=true"),
        ("starttls", "smtp", "True", "?skip_ssl_verify=true"),
    ],
)
def test_config_file_with_smtp_integration(
    harness: Harness,
    mocked_migration_is_needed: MagicMock,
    mocked_kratos_configmap: MagicMock,
    transport_security: str,
    method: str,
    skip_ssl_verify: str,
    additional_param: str,
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_smtp_relation(harness, transport_security, skip_ssl_verify)

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {
                    "id": "user_v0",
                    "url": f"base64://{base64.b64encode(json.dumps(IDENTITY_SCHEMA).encode()).decode()}",
                },
                {
                    "id": "user_v1",
                    "url": f"base64://{base64.b64encode(json.dumps(IDENTITY_SCHEMA).encode()).decode()}",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "default_browser_return_url": DEFAULT_BROWSER_RETURN_URL,
        },
        "courier": {
            "smtp": {
                "connection_uri": f"{method}://example_user:some-password@example.smtp:25/{additional_param}"
            },
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_config_changed_when_identity_schemas_config(
    harness: Harness, mocked_kratos_configmap: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    schema_id = "user_v0"
    harness.update_config({
        "identity_schemas": json.dumps({"user_v1": IDENTITY_SCHEMA, schema_id: IDENTITY_SCHEMA}),
        "default_identity_schema_id": schema_id,
    })

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": schema_id,
            "schemas": [
                {
                    "id": "user_v0",
                    "url": f"base64://{base64.b64encode(json.dumps(IDENTITY_SCHEMA).encode()).decode()}",
                },
                {
                    "id": "user_v1",
                    "url": f"base64://{base64.b64encode(json.dumps(IDENTITY_SCHEMA).encode()).decode()}",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "default_browser_return_url": DEFAULT_BROWSER_RETURN_URL,
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_config_changed_when_identity_schemas_config_unset(
    harness: Harness, mocked_kratos_configmap: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    schema_id = "user_v0"
    harness.update_config({
        "identity_schemas": json.dumps({"user_v1": IDENTITY_SCHEMA, schema_id: IDENTITY_SCHEMA}),
        "default_identity_schema_id": schema_id,
    })
    harness.update_config(unset=["identity_schemas", "default_identity_schema_id"])

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "default_browser_return_url": DEFAULT_BROWSER_RETURN_URL,
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_config_changed_when_local_idp_enabled_mfa_not_enforced(
    harness: Harness, mocked_kratos_configmap: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_ingress_relation(harness, "public")
    (_, login_databag) = setup_login_ui_relation(harness)
    harness.update_config({"enforce_mfa": False})

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "selfservice": {
            "allowed_return_urls": [
                "https://public/",
            ],
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_database_created_cannot_connect_container(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_database_created_when_pebble_is_ready_in_leader_unit_missing_peer_relation(
    harness: Harness,
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for peer relation" in harness.charm.unit.status.message


def test_on_database_created_updated_config_and_start_service_when_pebble_is_ready_in_leader_unit(
    harness: Harness, mocked_pebble_exec_success: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert isinstance(harness.charm.unit.status, ActiveStatus)

    pebble_env = harness.charm._pebble_layer.to_dict()["services"][CONTAINER_NAME]["environment"]
    assert DB_ENDPOINTS in pebble_env["DSN"]
    assert DB_PASSWORD in pebble_env["DSN"]
    assert DB_USERNAME in pebble_env["DSN"]


def test_on_database_created_updated_config_and_start_service_when_pebble_is_ready_in_non_leader_unit(
    harness: Harness, mocked_get_secret: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    harness.set_leader(False)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    harness.charm.on.kratos_pebble_ready.emit(container)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert isinstance(harness.charm.unit.status, ActiveStatus)

    pebble_env = harness.charm._pebble_layer.to_dict()["services"][CONTAINER_NAME]["environment"]
    assert DB_ENDPOINTS in pebble_env["DSN"]
    assert DB_PASSWORD in pebble_env["DSN"]
    assert DB_USERNAME in pebble_env["DSN"]


def test_on_database_created_not_run_migration_in_non_leader_unit(
    harness: Harness, mocked_pebble_exec: MagicMock
) -> None:
    harness.set_leader(False)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_postgres_relation(harness)

    mocked_pebble_exec.assert_not_called()


def test_on_database_created_pending_migration_in_non_leader_unit(
    harness: Harness, mocked_get_secret: MagicMock
) -> None:
    harness.set_leader(False)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Unit waiting for leadership to run the migration" in harness.charm.unit.status.message


def test_on_database_created_when_migration_is_successful(
    harness: Harness, mocked_pebble_exec_success: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert isinstance(harness.charm.unit.status, ActiveStatus)
    mocked_pebble_exec_success.assert_called_once()

    pebble_env = harness.charm._pebble_layer.to_dict()["services"][CONTAINER_NAME]["environment"]
    assert DB_ENDPOINTS in pebble_env["DSN"]
    assert DB_PASSWORD in pebble_env["DSN"]
    assert DB_USERNAME in pebble_env["DSN"]


def test_on_database_created_when_migration_failed(
    harness: Harness, mocked_pebble_exec_failed: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, BlockedStatus)


def test_on_database_changed_cannot_connect_container(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_database_changed_when_pebble_is_ready(
    harness: Harness, mocked_pebble_exec_success: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    pebble_env = harness.charm._pebble_layer.to_dict()["services"][CONTAINER_NAME]["environment"]
    assert DB_ENDPOINTS in pebble_env["DSN"]
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_on_config_changed_cannot_connect_container(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_config_changed_when_pebble_is_ready(
    harness: Harness, mocked_pebble_exec_success: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    pebble_env = harness.charm._pebble_layer.to_dict()["services"][CONTAINER_NAME]["environment"]
    assert DB_ENDPOINTS in pebble_env["DSN"]
    assert isinstance(harness.charm.unit.status, ActiveStatus)


@pytest.mark.parametrize("api_type,port", [("admin", 4434), ("public", 4433)])
def test_ingress_relation_created(
    harness: Harness, mocked_fqdn: MagicMock, api_type: str, port: int
) -> None:
    relation_id = setup_ingress_relation(harness, api_type)
    app_data = harness.get_relation_data(relation_id, harness.charm.app)

    assert app_data == {
        "model": json.dumps(harness.model.name),
        "name": json.dumps("kratos"),
        "port": json.dumps(port),
        "redirect-https": json.dumps(False),
        "scheme": json.dumps("http"),
        "strip-prefix": json.dumps(True),
    }


def test_on_config_changed_when_no_dns_available(harness: Harness) -> None:
    setup_postgres_relation(harness)
    setup_external_provider_relation(harness)

    assert isinstance(harness.charm.unit.status, BlockedStatus)


def test_on_client_config_changed_with_ingress(
    harness: Harness,
    mocked_container: Container,
    mocked_migration_is_needed: MagicMock,
    mocked_kratos_configmap: MagicMock,
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")
    (_, login_databag) = setup_login_ui_relation(harness)

    relation_id, data = setup_external_provider_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "allowed_return_urls": [
                "https://public/",
            ],
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
                "registration": {
                    "after": {
                        "oidc": {
                            "hooks": [
                                {
                                    "hook": "session",
                                },
                            ],
                        },
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
                "totp": {
                    "enabled": True,
                    "config": {
                        "issuer": "Identity Platform",
                    },
                },
                "lookup_secret": {
                    "enabled": True,
                },
                "oidc": {
                    "config": {
                        "providers": [
                            {
                                "id": data["provider_id"],
                                "client_id": data["client_id"],
                                "client_secret": data["client_secret"],
                                "issuer_url": data["issuer_url"],
                                "mapper_url": "file:///etc/config/kratos/default_schema.jsonnet",
                                "provider": data["provider"],
                                "label": data["label"],
                                "scope": data["scope"].split(" "),
                            },
                        ],
                    },
                    "enabled": True,
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )

    expected_redirect_url = harness.charm.public_ingress.url.replace(
        "http://", "https://"
    ).replace(":80", "")
    app_data = json.loads(harness.get_relation_data(relation_id, harness.charm.app)["providers"])

    assert app_data[0]["redirect_uri"].startswith(expected_redirect_url)


def test_on_client_config_relation_removed_with_ingress(
    harness: Harness,
    mocked_container: Container,
    mocked_migration_is_needed: MagicMock,
    mocked_kratos_configmap: MagicMock,
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")
    (_, login_databag) = setup_login_ui_relation(harness)

    relation_id, _ = setup_external_provider_relation(harness)
    harness.remove_relation(relation_id)
    harness.set_leader(True)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "allowed_return_urls": [
                "https://public/",
            ],
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
                "totp": {
                    "enabled": True,
                    "config": {
                        "issuer": "Identity Platform",
                    },
                },
                "lookup_secret": {
                    "enabled": True,
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_client_config_data_removed_with_ingress(
    harness: Harness,
    mocked_container: Container,
    mocked_migration_is_needed: MagicMock,
    mocked_kratos_configmap: MagicMock,
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")
    (_, login_databag) = setup_login_ui_relation(harness)

    relation_id, _ = setup_external_provider_relation(harness)
    harness.update_relation_data(relation_id, "kratos-external-idp-integrator", {"providers": ""})
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "allowed_return_urls": [
                "https://public/",
            ],
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
                "totp": {
                    "enabled": True,
                    "config": {
                        "issuer": "Identity Platform",
                    },
                },
                "lookup_secret": {
                    "enabled": True,
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )

    assert harness.get_relation_data(relation_id, harness.charm.app) == {}


def test_on_config_changed_with_hydra(
    harness: Harness, mocked_migration_is_needed: MagicMock, mocked_kratos_configmap: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    (_, login_databag) = setup_login_ui_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_hydra_relation(harness)

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
                "totp": {
                    "enabled": True,
                    "config": {
                        "issuer": "Identity Platform",
                    },
                },
                "lookup_secret": {
                    "enabled": True,
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
        "oauth2_provider": {
            "url": "http://hydra-admin-url:80/testing-hydra",
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_config_changed_when_missing_hydra_relation_data(
    harness: Harness, mocked_kratos_configmap: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    setup_postgres_relation(harness)
    setup_peer_relation(harness)
    _, login_databag = setup_login_ui_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    relation_id = harness.add_relation("hydra-endpoint-info", "hydra")
    harness.add_relation_unit(relation_id, "hydra/0")

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
                "totp": {
                    "enabled": True,
                    "config": {
                        "issuer": "Identity Platform",
                    },
                },
                "lookup_secret": {
                    "enabled": True,
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_changed_without_login_ui_endpoints(
    harness: Harness, mocked_migration_is_needed: MagicMock, mocked_kratos_configmap: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_hydra_relation(harness)

    login_ui_relation_id = harness.add_relation(
        "ui-endpoint-info", "identity-platform-login-ui-operator"
    )
    harness.add_relation_unit(login_ui_relation_id, "identity-platform-login-ui-operator/0")

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "default_browser_return_url": DEFAULT_BROWSER_RETURN_URL,
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
        "oauth2_provider": {
            "url": "http://hydra-admin-url:80/testing-hydra",
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_config_changed_when_missing_login_ui_and_hydra_relation_data(
    harness: Harness, mocked_kratos_configmap: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    setup_postgres_relation(harness)
    setup_peer_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    relation_id = harness.add_relation("hydra-endpoint-info", "hydra")
    harness.add_relation_unit(relation_id, "hydra/0")

    login_ui_relation_id = harness.add_relation(
        "ui-endpoint-info", "identity-platform-login-ui-operator"
    )
    harness.add_relation_unit(login_ui_relation_id, "identity-platform-login-ui-operator/0")

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "default_browser_return_url": DEFAULT_BROWSER_RETURN_URL,
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_config_changed_when_recovery_email_template_set(
    harness: Harness,
    mocked_kratos_configmap: MagicMock,
    mocked_migration_is_needed: MagicMock,
    mocked_recovery_email_template: MagicMock,
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    harness.update_config({"recovery_email_template": "some template"})

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    assert "templates" in config


def test_on_config_changed_when_local_idp_disabled(
    harness: Harness, mocked_kratos_configmap: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    (_, login_databag) = setup_login_ui_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_hydra_relation(harness)

    harness.update_config({"enable_local_idp": False})

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "selfservice": {
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                },
            },
            "methods": {
                "password": {
                    "enabled": False,
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
        "oauth2_provider": {
            "url": "http://hydra-admin-url:80/testing-hydra",
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_config_changed_when_webauthn_enabled(
    harness: Harness, mocked_kratos_configmap: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    (_, login_databag) = setup_login_ui_relation(harness)
    setup_ingress_relation(harness, "public")

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_hydra_relation(harness)

    harness.update_config({"enable_passwordless_login_method": True})

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "allowed_return_urls": [
                "https://public/",
            ],
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                    "after": {
                        "webauthn": {
                            "default_browser_return_url": login_databag["webauthn_settings_url"],
                        },
                    },
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
                "totp": {
                    "enabled": True,
                    "config": {
                        "issuer": "Identity Platform",
                    },
                },
                "lookup_secret": {
                    "enabled": True,
                },
                "webauthn": {
                    "enabled": True,
                    "config": {
                        "passwordless": True,
                        "rp": {
                            "id": "public",
                            "origins": ["https://public"],
                            "display_name": "Identity Platform",
                        },
                    },
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
        "oauth2_provider": {
            "url": "http://hydra-admin-url:80/testing-hydra",
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


def test_on_config_changed_when_oidc_webauthn_sequencing_and_passwordless_login_enabled(
    harness: Harness,
    mocked_get_secret: MagicMock,
    mocked_migration_is_needed: MagicMock,
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")

    harness.update_config({"enable_oidc_webauthn_sequencing": True})
    harness.update_config({"enable_passwordless_login_method": True})

    assert isinstance(harness.model.unit.status, BlockedStatus)
    assert (
        "OIDC-WebAuthn sequencing mode requires `enable_passwordless_login_method=False`. Please change the config."
        in harness.charm.unit.status.message
    )


def test_on_config_changed_when_oidc_webauthn_sequencing_enabled(
    harness: Harness, mocked_kratos_configmap: MagicMock, mocked_migration_is_needed: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    (_, login_databag) = setup_login_ui_relation(harness)
    setup_ingress_relation(harness, "public")

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_hydra_relation(harness)

    harness.update_config({"enable_oidc_webauthn_sequencing": True})

    expected_config = {
        "log": {
            "level": "info",
            "format": "json",
        },
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "base64://something"},
                {
                    "id": "social_user_v0",
                    "url": "base64://something",
                },
            ],
        },
        "session": {
            "whoami": {
                "required_aal": "highest_available",
            },
        },
        "selfservice": {
            "allowed_return_urls": [
                "https://public/",
            ],
            "default_browser_return_url": login_databag["login_url"],
            "flows": {
                "error": {
                    "ui_url": login_databag["error_url"],
                },
                "login": {
                    "ui_url": login_databag["login_url"],
                },
                "settings": {
                    "ui_url": login_databag["settings_url"],
                    "required_aal": "highest_available",
                    "after": {
                        "webauthn": {
                            "default_browser_return_url": login_databag["webauthn_settings_url"],
                        },
                    },
                },
                "recovery": {
                    "enabled": True,
                    "ui_url": login_databag["recovery_url"],
                    "use": "code",
                    "after": {
                        "default_browser_return_url": login_databag["login_url"],
                        "hooks": [
                            {
                                "hook": "revoke_active_sessions",
                            },
                        ],
                    },
                },
            },
            "methods": {
                "code": {
                    "enabled": True,
                },
                "password": {
                    "enabled": True,
                    "config": {
                        "haveibeenpwned_enabled": False,
                    },
                },
                "totp": {
                    "enabled": True,
                    "config": {
                        "issuer": "Identity Platform",
                    },
                },
                "lookup_secret": {
                    "enabled": True,
                },
                "webauthn": {
                    "enabled": True,
                    "config": {
                        "passwordless": False,
                        "rp": {
                            "id": "public",
                            "origins": ["https://public"],
                            "display_name": "Identity Platform",
                        },
                    },
                },
            },
        },
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "cors": {
                    "enabled": True,
                },
            },
        },
        "oauth2_provider": {
            "url": "http://hydra-admin-url:80/testing-hydra",
        },
    }

    configmap = mocked_kratos_configmap.update.call_args_list[-1][0][0]
    config = configmap["kratos.yaml"]
    validate_config(
        expected_config, yaml.safe_load(config), validate_schemas=False, validate_mappers=False
    )


@pytest.mark.parametrize(
    "action",
    [
        "_on_get_identity_action",
        "_on_delete_identity_action",
        "_on_reset_password_action",
        "_on_create_admin_account_action",
        "_on_run_migration_action",
        "_on_invalidate_identity_sessions_action",
        "_on_reset_identity_mfa_action",
    ],
)
def test_actions_when_cannot_connect(harness: Harness, action: str) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    event = MagicMock()

    getattr(harness.charm, action)(event)

    event.fail.assert_called_with(
        "Service is not ready. Please re-run the action when the charm is active"
    )


def test_get_identity_action_with_identity_id(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_get_identity: MagicMock
) -> None:
    identity_id = mocked_get_identity.return_value["id"]
    event = MagicMock()
    event.params = {"identity-id": identity_id}

    harness.charm._on_get_identity_action(event)

    event.set_results.assert_called()


def test_error_on_get_identity_action_with_identity_id(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_get_identity: MagicMock
) -> None:
    mocked_get_identity.side_effect = ExecError(
        command=["kratos", "get", "identity"], exit_code=1, stdout="", stderr="Error"
    )
    event = MagicMock()
    event.params = {"identity-id": "identity_id"}

    harness.charm._on_get_identity_action(event)

    event.fail.assert_called()


def test_get_identity_action_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
) -> None:
    email = mocked_get_identity_from_email.return_value["traits"]["email"]
    event = MagicMock()
    event.params = {"email": email}

    harness.charm._on_get_identity_action(event)

    event.set_results.assert_called()


def test_get_identity_action_with_wrong_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
) -> None:
    mocked_get_identity_from_email.return_value = None
    event = MagicMock()
    event.params = {"email": "email"}

    harness.charm._on_get_identity_action(event)

    event.fail.assert_called_with("Couldn't retrieve identity_id from email.")
    event.set_results.assert_not_called()


def test_error_on_get_identity_action_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
) -> None:
    mocked_get_identity_from_email.side_effect = ExecError(
        command=["kratos", "list", "identities"], exit_code=1, stdout="", stderr="Error"
    )
    event = MagicMock()
    event.params = {"email": "email"}

    harness.charm._on_get_identity_action(event)

    event.fail.assert_called()


def test_delete_identity_action_with_identity_id(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_delete_identity: MagicMock
) -> None:
    identity_id = mocked_delete_identity.return_value
    event = MagicMock()
    event.params = {"identity-id": identity_id}

    harness.charm._on_delete_identity_action(event)

    event.set_results.assert_called()


def test_error_on_delete_identity_action_with_identity_id(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_delete_identity: MagicMock
) -> None:
    mocked_delete_identity.side_effect = ExecError(
        command=["kratos", "delete", "identity"], exit_code=1, stdout="", stderr="Error"
    )
    event = MagicMock()
    event.params = {"identity-id": "identity_id"}

    harness.charm._on_delete_identity_action(event)

    event.fail.assert_called()


def test_delete_identity_action_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_delete_identity: MagicMock,
) -> None:
    email = mocked_get_identity_from_email.return_value["traits"]["email"]
    event = MagicMock()
    event.params = {"email": email}

    harness.charm._on_delete_identity_action(event)

    event.set_results.assert_called()


def test_error_on_delete_identity_action_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_delete_identity: MagicMock,
) -> None:
    mocked_delete_identity.side_effect = ExecError(
        command=["kratos", "delete", "identity"], exit_code=1, stdout="", stderr="Error"
    )
    event = MagicMock()
    event.params = {"email": "email"}

    harness.charm._on_delete_identity_action(event)

    event.fail.assert_called()


def test_reset_password_action_when_password_secret_id_provided_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_reset_password: MagicMock,
) -> None:
    secret_content = {"password": "some-password"}
    secret_id = harness.add_user_secret(secret_content)
    harness.grant_secret(secret_id, "kratos")

    event = MagicMock()
    event.params = {"identity-id": "123", "password-secret-id": secret_id}

    harness.charm._on_reset_password_action(event)

    event.set_results.assert_called()


def test_error_on_reset_password_action_when_password_secret_id_provided_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_reset_password: MagicMock,
) -> None:
    secret_content = {"password": "some-password"}
    secret_id = harness.add_user_secret(secret_content)
    harness.grant_secret(secret_id, "kratos")

    mocked_reset_password.side_effect = requests.exceptions.HTTPError("error")
    event = MagicMock()
    event.params = {"identity-id": "123", "password-secret-id": secret_id}

    harness.charm._on_reset_password_action(event)

    event.fail.assert_called_with("Failed to request Kratos API: error")


def test_reset_password_action_when_password_secret_id_invalid_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_reset_password: MagicMock,
) -> None:
    event = MagicMock()
    event.params = {"identity-id": "123", "password-secret-id": "invalid-juju-secret-id"}

    harness.charm._on_reset_password_action(event)

    event.fail.assert_called_with("Secret not found")


def test_reset_password_action_when_password_secret_id_provided_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_reset_password: MagicMock,
) -> None:
    secret_content = {"password": "some-password"}
    secret_id = harness.add_user_secret(secret_content)
    harness.grant_secret(secret_id, "kratos")

    event = MagicMock()
    event.params = {"email": "test@example.com", "password-secret-id": secret_id}

    harness.charm._on_reset_password_action(event)

    event.set_results.assert_called()


def test_error_on_reset_password_action_when_password_secret_id_provided_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_reset_password: MagicMock,
) -> None:
    secret_content = {"password": "some-password"}
    secret_id = harness.add_user_secret(secret_content)
    harness.grant_secret(secret_id, "kratos")

    mocked_reset_password.side_effect = requests.exceptions.HTTPError("error")
    event = MagicMock()
    event.params = {"email": "test@example.com", "password-secret-id": secret_id}

    harness.charm._on_reset_password_action(event)

    event.fail.assert_called_with("Failed to request Kratos API: error")


def test_reset_password_action_with_code_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_recover_password_with_code: MagicMock,
) -> None:
    identity_id = mocked_recover_password_with_code.return_value
    event = MagicMock()
    event.params = {"identity-id": identity_id}

    harness.charm._on_reset_password_action(event)

    event.set_results.assert_called()


def test_error_on_reset_password_action_with_code_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_recover_password_with_code: MagicMock,
) -> None:
    mocked_recover_password_with_code.side_effect = requests.exceptions.HTTPError()
    event = MagicMock()
    event.params = {"identity-id": "identity_id"}

    harness.charm._on_reset_password_action(event)

    event.fail.assert_called()


def test_reset_password_action_with_code_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_recover_password_with_code: MagicMock,
) -> None:
    identity_id = mocked_recover_password_with_code.return_value
    event = MagicMock()
    event.params = {"identity-id": identity_id}

    harness.charm._on_reset_password_action(event)

    event.set_results.assert_called()


def test_error_on_reset_mfa_action_with_identity_id_when_mfa_type_not_provided(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_delete_mfa_credential: MagicMock,
) -> None:
    event = MagicMock()
    event.params = {"identity-id": "123"}

    harness.charm._on_reset_identity_mfa_action(event)

    event.fail.assert_called_with("MFA type must be specified")


def test_error_on_reset_mfa_action_with_identity_id_when_mfa_type_uncorrect(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_delete_mfa_credential: MagicMock,
) -> None:
    event = MagicMock()
    unsupported_type = "test"
    event.params = {"identity-id": "123", "mfa-type": unsupported_type}

    harness.charm._on_reset_identity_mfa_action(event)

    event.fail.assert_called_with(
        f"Unsupported MFA credential type {unsupported_type}, allowed methods are: `totp`, `lookup_secret` and `webauthn`"
    )


@pytest.mark.parametrize("mfa_type", ["totp", "lookup_secret", "webauthn"])
def test_reset_mfa_action_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_delete_mfa_credential: MagicMock,
    mfa_type: str,
) -> None:
    params = {"identity-id": "123", "mfa-type": mfa_type}

    action_output = harness.run_action("reset-identity-mfa", params)

    assert "Second authentication factor was reset" in action_output.logs


@pytest.mark.parametrize("mfa_type", ["totp", "lookup_secret", "webauthn"])
def test_reset_mfa_action_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_delete_mfa_credential: MagicMock,
    mfa_type: str,
) -> None:
    params = {"email": "test@example.com", "mfa-type": mfa_type}

    action_output = harness.run_action("reset-identity-mfa", params)

    assert "Second authentication factor was reset" in action_output.logs


@pytest.mark.parametrize("mfa_type", ["totp", "lookup_secret", "webauthn"])
def test_reset_mfa_action_with_identity_id_when_no_credentials(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_delete_mfa_credential: MagicMock,
    mfa_type: str,
) -> None:
    mocked_delete_mfa_credential.return_value = False
    params = {"identity-id": "123", "mfa-type": mfa_type}

    action_output = harness.run_action("reset-identity-mfa", params)

    assert f"User has no {mfa_type} credentials" in action_output.logs


@pytest.mark.parametrize("mfa_type", ["totp", "lookup_secret", "webauthn"])
def test_reset_mfa_action_with_email_when_no_credentials(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_delete_mfa_credential: MagicMock,
    mfa_type: str,
) -> None:
    mocked_delete_mfa_credential.return_value = False
    params = {"email": "test@example.com", "mfa-type": mfa_type}

    action_output = harness.run_action("reset-identity-mfa", params)

    assert f"User has no {mfa_type} credentials" in action_output.logs


def test_error_on_reset_mfa_action_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_delete_mfa_credential: MagicMock,
) -> None:
    event = MagicMock()
    mocked_delete_mfa_credential.side_effect = requests.exceptions.HTTPError()
    event.params = {"identity-id": "123"}

    harness.charm._on_reset_identity_mfa_action(event)

    event.fail.assert_called()


def test_invalidate_sessions_action_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_invalidate_sessions: MagicMock,
) -> None:
    params = {"identity-id": "123"}

    action_output = harness.run_action("invalidate-identity-sessions", params)

    assert "User sessions have been invalidated and deleted" in action_output.logs


def test_invalidate_sessions_action_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_invalidate_sessions: MagicMock,
) -> None:
    params = {"email": "test@example.com"}

    action_output = harness.run_action("invalidate-identity-sessions", params)

    assert "User sessions have been invalidated and deleted" in action_output.logs


def test_invalidate_sessions_action_with_identity_id_when_no_sessions(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_invalidate_sessions: MagicMock,
) -> None:
    mocked_invalidate_sessions.return_value = False
    params = {"identity-id": "123"}

    action_output = harness.run_action("invalidate-identity-sessions", params)

    assert "User has no sessions" in action_output.logs


def test_invalidate_sessions_action_with_email_when_no_sessions(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_invalidate_sessions: MagicMock,
) -> None:
    mocked_invalidate_sessions.return_value = False
    params = {"email": "test@example.com"}

    action_output = harness.run_action("invalidate-identity-sessions", params)

    assert "User has no sessions" in action_output.logs


def test_error_on_invalidate_sessions_action_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_invalidate_sessions: MagicMock,
) -> None:
    event = MagicMock()
    mocked_invalidate_sessions.side_effect = requests.exceptions.HTTPError()
    event.params = {"identity-id": "123"}

    harness.charm._on_invalidate_identity_sessions_action(event)

    event.fail.assert_called()


def test_create_admin_account_with_password(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_create_identity: MagicMock,
    password_secret: Tuple[str, str],
) -> None:
    identity_id = mocked_create_identity.return_value["id"]
    event = MagicMock()
    event.params = {"username": "username", "password-secret-id": password_secret[1]}

    harness.charm._on_create_admin_account_action(event)

    event.set_results.assert_called_with({"identity-id": identity_id})


def test_create_admin_account_without_password(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_create_identity: MagicMock,
    mocked_recover_password_with_code: MagicMock,
) -> None:
    event = MagicMock()
    event.params = {"username": "username"}

    harness.charm._on_create_admin_account_action(event)

    event.set_results.assert_called_with({
        "identity-id": mocked_create_identity.return_value["id"],
        "password-reset-link": mocked_recover_password_with_code.return_value["recovery_link"],
        "password-reset-code": mocked_recover_password_with_code.return_value["recovery_code"],
        "expires-at": mocked_recover_password_with_code.return_value["expires_at"],
    })


def test_run_migration_action(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_run_migration: MagicMock
) -> None:
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    event = MagicMock()

    harness.charm._on_run_migration_action(event)

    mocked_run_migration.assert_called_once()
    event.fail.assert_not_called()


def test_error_on_run_migration_action(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_run_migration: MagicMock
) -> None:
    mocked_run_migration.side_effect = ExecError(
        command=[], exit_code=1, stdout="", stderr="Error"
    )
    event = MagicMock()

    harness.charm._on_run_migration_action(event)

    mocked_run_migration.assert_called_once()
    event.fail.assert_called()


def test_timeout_on_run_migration_action(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_run_migration: MagicMock
) -> None:
    mocked_run_migration.side_effect = TimeoutError
    event = MagicMock()

    harness.charm._on_run_migration_action(event)

    mocked_run_migration.assert_called_once()
    event.fail.assert_called()


def test_on_pebble_ready_with_loki(
    harness: Harness, mocked_migration_is_needed: MagicMock
) -> None:
    setup_postgres_relation(harness)
    setup_peer_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.leader_elected.emit()
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_loki_relation(harness)

    assert harness.model.unit.status == ActiveStatus()


def test_on_pebble_ready_with_bad_config(harness: Harness) -> None:
    setup_postgres_relation(harness)
    harness.update_config({"log_level": "invalid_config"})
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, BlockedStatus)
    assert "Invalid configuration value for log_level" in harness.charm.unit.status.message


def test_on_config_changed_with_invalid_log_level(harness: Harness) -> None:
    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")

    harness.update_config({"log_level": "invalid_config"})

    assert isinstance(harness.model.unit.status, BlockedStatus)
    assert "Invalid configuration value for log_level" in harness.charm.unit.status.message


def test_layer_updated_with_tracing_endpoint_info(harness: Harness) -> None:
    """Test Pebble Layer when relation data is in place."""
    harness.set_leader(True)
    harness.set_can_connect(CONTAINER_NAME, True)
    harness.charm.on.kratos_pebble_ready.emit(CONTAINER_NAME)
    setup_tempo_relation(harness)

    pebble_env = harness.charm._pebble_layer.to_dict()["services"][CONTAINER_NAME]["environment"]

    assert (
        pebble_env["TRACING_PROVIDERS_OTLP_SERVER_URL"]
        == "tempo-k8s-0.tempo-k8s-endpoints.namespace.svc.cluster.local:4318"
    )
    assert pebble_env["TRACING_PROVIDERS_OTLP_INSECURE"]
    assert pebble_env["TRACING_PROVIDERS_OTLP_SAMPLING_SAMPLING_RATIO"] == 1
    assert pebble_env["TRACING_PROVIDER"] == "otel"


def test_kratos_info_ready_event_emitted_when_relation_created(harness: Harness) -> None:
    with capture_events(harness.charm, KratosInfoRelationReadyEvent) as captured:
        _ = setup_kratos_info_relation(harness)

    assert any(isinstance(e, KratosInfoRelationReadyEvent) for e in captured)


def test_kratos_info_updated_on_relation_ready(harness: Harness) -> None:
    harness.charm.info_provider.send_info_relation_data = mocked_handle = Mock(return_value=None)
    _ = setup_kratos_info_relation(harness)
    setup_ingress_relation(harness, "public")

    mocked_handle.assert_called_with(
        "http://kratos.kratos-model.svc.cluster.local:4434",
        "http://kratos.kratos-model.svc.cluster.local:4433",
        "https://public/kratos-model-kratos",
        "providers",
        "identity-schemas",
        "kratos-model",
        True,
        False,
    )


def test_on_pebble_ready_correct_plan_with_proxy_flags_when_set(
    harness: Harness,
    mocked_migration_is_needed: MagicMock,
    mocked_get_secret: MagicMock,
) -> None:
    proxy = "http://proxy.internal:6666"
    no_proxy = "google.com,github.com"
    harness.update_config({"http_proxy": proxy, "https_proxy": proxy, "no_proxy": no_proxy})
    container = harness.model.unit.get_container(CONTAINER_NAME)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    harness.charm.on.kratos_pebble_ready.emit(container)

    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    environment = updated_plan["services"][CONTAINER_NAME].pop("environment")
    assert environment["HTTP_PROXY"] == proxy
    assert environment["HTTPS_PROXY"] == proxy
    assert environment["NO_PROXY"] == no_proxy


def test_on_pebble_ready_correct_plan_with_proxy_flags_when_unset(
    harness: Harness,
    mocked_migration_is_needed: MagicMock,
    mocked_get_secret: MagicMock,
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)
    harness.charm.on.kratos_pebble_ready.emit(container)

    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    environment = updated_plan["services"][CONTAINER_NAME].pop("environment")
    assert environment["HTTP_PROXY"] == ""
    assert environment["HTTPS_PROXY"] == ""
    assert environment["NO_PROXY"] == ""


def test_kratos_info_updated_on_internal_ingress_relation_joined(harness: Harness) -> None:
    kratos_info_relation_id = setup_kratos_info_relation(harness)

    setup_ingress_relation(harness, "public")
    _ = setup_internal_ingress_relation(harness, "admin")

    ingress_url = f"{harness.charm.internal_ingress.scheme}://{harness.charm.internal_ingress.external_host}/{harness.model.name}-{harness.model.app.name}"

    info_data = harness.get_relation_data(kratos_info_relation_id, harness.charm.app)

    assert info_data["admin_endpoint"] == ingress_url
    assert info_data["public_endpoint"] == ingress_url


def test_kratos_info_updated_on_internal_ingress_relation_changed(harness: Harness) -> None:
    kratos_info_relation_id = setup_kratos_info_relation(harness)

    setup_ingress_relation(harness, "public")
    relation_id = setup_internal_ingress_relation(harness, "admin")

    url_change = "new-test.staging.canonical.com"
    harness.update_relation_data(
        relation_id,
        "admin-traefik",
        {"external_host": url_change, "scheme": "https"},
    )

    ingress_url = f"{harness.charm.internal_ingress.scheme}://{url_change}/{harness.model.name}-{harness.model.app.name}"

    info_data = harness.get_relation_data(kratos_info_relation_id, harness.charm.app)

    assert info_data["admin_endpoint"] == ingress_url
    assert info_data["public_endpoint"] == ingress_url


def test_kratos_info_updated_on_internal_ingress_relation_broken(harness: Harness) -> None:
    kratos_info_relation_id = setup_kratos_info_relation(harness)

    setup_ingress_relation(harness, "public")
    relation_id = setup_internal_ingress_relation(harness, "admin")

    harness.remove_relation(relation_id)

    info_data = harness.get_relation_data(kratos_info_relation_id, harness.charm.app)

    assert info_data["admin_endpoint"] == "http://kratos.kratos-model.svc.cluster.local:4434"
    assert info_data["public_endpoint"] == "http://kratos.kratos-model.svc.cluster.local:4433"
