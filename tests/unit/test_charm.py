# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import base64
import json
from unittest.mock import MagicMock

import pytest
import requests
import yaml
from ops.model import ActiveStatus, BlockedStatus, Container, WaitingStatus
from ops.pebble import ExecError, TimeoutError
from ops.testing import Harness

from charm import DB_MIGRATE_VERSION, PEER_KEY_DB_MIGRATE_VERSION

CONTAINER_NAME = "kratos"
DB_USERNAME = "fake_relation_id_1"
DB_PASSWORD = "fake-password"
DB_ENDPOINTS = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"
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


def setup_postgres_relation(harness: Harness) -> None:
    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")
    harness.update_relation_data(
        db_relation_id,
        "postgresql-k8s",
        {
            "data": '{"database": "database", "extra-user-roles": "SUPERUSER"}',
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


def setup_peer_relation(harness: Harness) -> None:
    rel_id = harness.add_relation("kratos-peers", "kratos")
    harness.add_relation_unit(rel_id, "kratos/1")
    harness.update_relation_data(
        rel_id,
        "kratos",
        {PEER_KEY_DB_MIGRATE_VERSION: DB_MIGRATE_VERSION},
    )


def setup_hydra_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("endpoint-info", "hydra")
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


def setup_external_provider_relation(harness: Harness) -> int:
    relation_id = harness.add_relation("kratos-external-idp", "kratos-external-idp-integrator")
    harness.add_relation_unit(relation_id, "kratos-external-idp-integrator/0")
    harness.update_relation_data(
        relation_id,
        "kratos-external-idp-integrator",
        {
            "providers": json.dumps(
                [
                    {
                        "client_id": "client_id",
                        "provider": "generic",
                        "secret_backend": "relation",
                        "client_secret": "client_secret",
                        "issuer_url": "https://example.com/oidc",
                    },
                ],
            ),
        },
    )
    return relation_id


def test_on_pebble_ready_cannot_connect_container(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, WaitingStatus)


def test_on_pebble_ready_correct_plan(harness: Harness) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_plan = {
        "services": {
            CONTAINER_NAME: {
                "override": "replace",
                "summary": "Kratos Operator layer",
                "startup": "disabled",
                "command": "kratos serve all --config /etc/config/kratos.yaml",
            }
        }
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    assert expected_plan == updated_plan


def test_on_pebble_ready_correct_plan_with_dev_flag(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    harness.update_config({"dev": True})
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_plan = {
        "services": {
            CONTAINER_NAME: {
                "override": "replace",
                "summary": "Kratos Operator layer",
                "startup": "disabled",
                "command": "kratos serve all --config /etc/config/kratos.yaml --dev",
            }
        }
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    assert expected_plan == updated_plan
    assert "Running Kratos in dev mode, don't do this in production" in caplog.messages


def test_on_pebble_ready_service_not_started_when_database_not_created(harness: Harness) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert not service.is_running()


def test_on_pebble_ready_service_started_when_database_is_created(harness: Harness) -> None:
    setup_postgres_relation(harness)
    setup_peer_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert harness.model.unit.status == ActiveStatus()


def test_on_pebble_ready_has_correct_config_when_database_is_created(harness: Harness) -> None:
    setup_postgres_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "file:///etc/config/schemas/default/admin_v0.json"},
                {
                    "id": "social_user_v0",
                    "url": "file:///etc/config/schemas/default/social_user_v0.json",
                },
            ],
        },
        "selfservice": {
            "default_browser_return_url": "http://127.0.0.1:4455/",
            "flows": {
                "error": {
                    "ui_url": "http://127.0.0.1:4455/oidc_error",
                },
                "login": {
                    "ui_url": "http://127.0.0.1:4455/login",
                },
                "registration": {
                    "enabled": True,
                    "ui_url": "http://127.0.0.1:4455/registration",
                },
            },
        },
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/{harness.model.name}_{harness.charm.app.name}",
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "base_url": "None",
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    assert yaml.safe_load(harness.charm._render_conf_file()) == expected_config


def test_on_pebble_ready_when_missing_database_relation(harness: Harness) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, BlockedStatus)
    assert "Missing postgres database relation" in harness.charm.unit.status.message


def test_on_pebble_ready_when_database_not_created_yet(harness: Harness) -> None:
    trigger_database_changed(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, WaitingStatus)
    assert "Waiting for database creation" in harness.charm.unit.status.message


def test_on_config_changed_when_identity_schemas_config(harness: Harness) -> None:
    setup_postgres_relation(harness)
    schema_id = "user_v0"
    harness.update_config(
        dict(
            identity_schemas=json.dumps({"user_v1": IDENTITY_SCHEMA, schema_id: IDENTITY_SCHEMA}),
            default_identity_schema=schema_id,
        )
    )

    expected_config = {
        "log": {"level": "trace"},
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
        "selfservice": {
            "default_browser_return_url": "http://127.0.0.1:4455/",
            "flows": {
                "error": {
                    "ui_url": "http://127.0.0.1:4455/oidc_error",
                },
                "login": {
                    "ui_url": "http://127.0.0.1:4455/login",
                },
                "registration": {
                    "enabled": True,
                    "ui_url": "http://127.0.0.1:4455/registration",
                },
            },
        },
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/{harness.model.name}_{harness.charm.app.name}",
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "base_url": "None",
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    assert yaml.safe_load(harness.charm._render_conf_file()) == expected_config


def test_on_config_changed_when_identity_schemas_config_unset(harness: Harness) -> None:
    setup_postgres_relation(harness)
    schema_id = "user_v0"
    harness.update_config(
        dict(
            identity_schemas=json.dumps({"user_v1": IDENTITY_SCHEMA, schema_id: IDENTITY_SCHEMA}),
            default_identity_schema=schema_id,
        )
    )
    harness.update_config(unset=["identity_schemas", "default_identity_schema"])

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "file:///etc/config/schemas/default/admin_v0.json"},
                {
                    "id": "social_user_v0",
                    "url": "file:///etc/config/schemas/default/social_user_v0.json",
                },
            ],
        },
        "selfservice": {
            "default_browser_return_url": "http://127.0.0.1:4455/",
            "flows": {
                "error": {
                    "ui_url": "http://127.0.0.1:4455/oidc_error",
                },
                "login": {
                    "ui_url": "http://127.0.0.1:4455/login",
                },
                "registration": {
                    "enabled": True,
                    "ui_url": "http://127.0.0.1:4455/registration",
                },
            },
        },
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/{harness.model.name}_{harness.charm.app.name}",
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "base_url": "None",
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    assert yaml.safe_load(harness.charm._render_conf_file()) == expected_config


def test_on_database_created_cannot_connect_container(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_database_created_when_pebble_is_not_ready(
    harness: Harness, mocked_pebble_exec_success: MagicMock
) -> None:
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for Kratos service" in harness.charm.unit.status.message
    mocked_pebble_exec_success.assert_not_called()


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
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert isinstance(harness.charm.unit.status, ActiveStatus)

    updated_config = yaml.safe_load(harness.charm._render_conf_file())
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert DB_PASSWORD in updated_config["dsn"]
    assert DB_USERNAME in updated_config["dsn"]


def test_on_database_created_updated_config_and_start_service_when_pebble_is_ready_in_non_leader_unit(
    harness: Harness,
) -> None:
    harness.set_leader(False)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert isinstance(harness.charm.unit.status, ActiveStatus)

    updated_config = yaml.safe_load(harness.charm._render_conf_file())
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert DB_PASSWORD in updated_config["dsn"]
    assert DB_USERNAME in updated_config["dsn"]


def test_on_database_created_not_run_migration_in_non_leader_unit(
    harness: Harness, mocked_pebble_exec: MagicMock
) -> None:
    harness.set_leader(False)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_postgres_relation(harness)

    mocked_pebble_exec.assert_not_called()


def test_on_database_created_pending_migration_in_non_leader_unit(harness: Harness) -> None:
    harness.set_leader(False)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    rel_id = harness.add_relation("kratos-peers", "kratos")
    harness.add_relation_unit(rel_id, "kratos/1")

    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for database migration to complete" in harness.charm.unit.status.message


def test_on_database_created_when_migration_is_successful(
    harness: Harness, mocked_pebble_exec_success: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert isinstance(harness.charm.unit.status, ActiveStatus)
    mocked_pebble_exec_success.assert_called_once()

    updated_config = yaml.safe_load(harness.charm._render_conf_file())
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert DB_PASSWORD in updated_config["dsn"]
    assert DB_USERNAME in updated_config["dsn"]


def test_on_database_created_when_migration_failed(
    harness: Harness, mocked_pebble_exec_failed: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, BlockedStatus)


def test_on_database_changed_cannot_connect_container(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_database_changed_when_pebble_is_not_ready(harness: Harness) -> None:
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for Kratos service" in harness.charm.unit.status.message


def test_on_database_changed_when_pebble_is_ready(
    harness: Harness, mocked_pebble_exec_success: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    updated_config = yaml.safe_load(harness.charm._render_conf_file())
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_on_config_changed_cannot_connect_container(harness: Harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_config_changed_when_pebble_is_not_ready(harness: Harness) -> None:
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for Kratos service" in harness.charm.unit.status.message


def test_on_config_changed_when_pebble_is_ready(
    harness: Harness, mocked_pebble_exec_success: MagicMock
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    updated_config = yaml.safe_load(harness.charm._render_conf_file())
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert isinstance(harness.charm.unit.status, ActiveStatus)


@pytest.mark.parametrize("api_type,port", [("admin", "4434"), ("public", "4433")])
def test_ingress_relation_created(
    harness: Harness, mocked_fqdn: MagicMock, api_type: str, port: str
) -> None:
    relation_id = setup_ingress_relation(harness, api_type)
    app_data = harness.get_relation_data(relation_id, harness.charm.app)

    assert app_data == {
        "host": mocked_fqdn.return_value,
        "model": harness.model.name,
        "name": "kratos",
        "port": port,
        "strip-prefix": "true",
    }


def test_on_client_config_changed_when_no_dns_available(harness: Harness) -> None:
    setup_postgres_relation(harness)
    setup_external_provider_relation(harness)

    assert isinstance(harness.charm.unit.status, BlockedStatus)


def test_on_client_config_changed_with_ingress(
    harness: Harness, mocked_container: Container
) -> None:
    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")
    relation_id = setup_external_provider_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "file:///etc/config/schemas/default/admin_v0.json"},
                {
                    "id": "social_user_v0",
                    "url": "file:///etc/config/schemas/default/social_user_v0.json",
                },
            ],
        },
        "selfservice": {
            "default_browser_return_url": "http://127.0.0.1:4455/",
            "flows": {
                "error": {
                    "ui_url": "http://127.0.0.1:4455/oidc_error",
                },
                "login": {
                    "ui_url": "http://127.0.0.1:4455/login",
                },
                "registration": {
                    "enabled": True,
                    "after": {"oidc": {"hooks": [{"hook": "session"}]}},
                    "ui_url": "http://127.0.0.1:4455/registration",
                },
            },
            "methods": {
                "password": {
                    "enabled": False,
                },
                "oidc": {
                    "config": {
                        "providers": [
                            {
                                "id": "generic_9d07bcc95549089d7f16120e8bed5396469a5426",
                                "client_id": "client_id",
                                "client_secret": "client_secret",
                                "issuer_url": "https://example.com/oidc",
                                "mapper_url": "file:///etc/config/claim_mappers/default_schema.jsonnet",
                                "provider": "generic",
                                "scope": ["profile", "email", "address", "phone"],
                            },
                        ],
                    },
                    "enabled": True,
                },
            },
        },
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/kratos-model_kratos",
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "base_url": "http://public:80/kratos-model-kratos",
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    app_data = json.loads(harness.get_relation_data(relation_id, harness.charm.app)["providers"])

    container_config = container.pull(path="/etc/config/kratos.yaml", encoding="utf-8")
    assert yaml.load(container_config.read(), yaml.Loader) == expected_config
    assert app_data[0]["redirect_uri"].startswith(harness.charm.public_ingress.url)


def test_on_client_config_changed_with_external_url_config(
    harness: Harness, mocked_container: Container
) -> None:
    # This is the provider id that will be computed based on the provider config
    provider_id = "generic_9d07bcc95549089d7f16120e8bed5396469a5426"
    harness.update_config({"external_url": "https://example.com"})
    setup_postgres_relation(harness)
    relation_id = setup_external_provider_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "file:///etc/config/schemas/default/admin_v0.json"},
                {
                    "id": "social_user_v0",
                    "url": "file:///etc/config/schemas/default/social_user_v0.json",
                },
            ],
        },
        "selfservice": {
            "default_browser_return_url": "http://127.0.0.1:4455/",
            "flows": {
                "error": {
                    "ui_url": "http://127.0.0.1:4455/oidc_error",
                },
                "login": {
                    "ui_url": "http://127.0.0.1:4455/login",
                },
                "registration": {
                    "enabled": True,
                    "after": {"oidc": {"hooks": [{"hook": "session"}]}},
                    "ui_url": "http://127.0.0.1:4455/registration",
                },
            },
            "methods": {
                "password": {
                    "enabled": False,
                },
                "oidc": {
                    "config": {
                        "providers": [
                            {
                                "id": provider_id,
                                "client_id": "client_id",
                                "client_secret": "client_secret",
                                "issuer_url": "https://example.com/oidc",
                                "mapper_url": "file:///etc/config/claim_mappers/default_schema.jsonnet",
                                "provider": "generic",
                                "scope": ["profile", "email", "address", "phone"],
                            },
                        ],
                    },
                    "enabled": True,
                },
            },
        },
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/kratos-model_kratos",
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "base_url": "https://example.com",
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    app_data = json.loads(harness.get_relation_data(relation_id, harness.charm.app)["providers"])

    container_config = container.pull(path="/etc/config/kratos.yaml", encoding="utf-8")
    assert yaml.load(container_config.read(), yaml.Loader) == expected_config
    assert app_data == [
        {
            "provider_id": provider_id,
            "redirect_uri": f'{harness.charm.config["external_url"]}/self-service/methods/oidc/callback/{provider_id}',
        }
    ]


def test_on_client_config_changed_with_hydra(harness: Harness) -> None:
    setup_postgres_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_hydra_relation(harness)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "file:///etc/config/schemas/default/admin_v0.json"},
                {
                    "id": "social_user_v0",
                    "url": "file:///etc/config/schemas/default/social_user_v0.json",
                },
            ],
        },
        "selfservice": {
            "default_browser_return_url": "http://127.0.0.1:4455/",
            "flows": {
                "error": {
                    "ui_url": "http://127.0.0.1:4455/oidc_error",
                },
                "login": {
                    "ui_url": "http://127.0.0.1:4455/login",
                },
                "registration": {
                    "enabled": True,
                    "ui_url": "http://127.0.0.1:4455/registration",
                },
            },
        },
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/{harness.model.name}_{harness.charm.app.name}",
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "base_url": "None",
                "cors": {
                    "enabled": True,
                },
            },
        },
        "oauth2_provider": {
            "url": "http://hydra-admin-url:80/testing-hydra",
        },
    }

    container_config = container.pull(path="/etc/config/kratos.yaml", encoding="utf-8")
    assert yaml.load(container_config.read(), yaml.Loader) == expected_config


def test_on_client_config_changed_when_missing_hydra_relation_data(harness: Harness) -> None:
    setup_postgres_relation(harness)
    setup_peer_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    relation_id = harness.add_relation("endpoint-info", "hydra")
    harness.add_relation_unit(relation_id, "hydra/0")

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "social_user_v0",
            "schemas": [
                {"id": "admin_v0", "url": "file:///etc/config/schemas/default/admin_v0.json"},
                {
                    "id": "social_user_v0",
                    "url": "file:///etc/config/schemas/default/social_user_v0.json",
                },
            ],
        },
        "selfservice": {
            "default_browser_return_url": "http://127.0.0.1:4455/",
            "flows": {
                "error": {
                    "ui_url": "http://127.0.0.1:4455/oidc_error",
                },
                "login": {
                    "ui_url": "http://127.0.0.1:4455/login",
                },
                "registration": {
                    "enabled": True,
                    "ui_url": "http://127.0.0.1:4455/registration",
                },
            },
        },
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/{harness.model.name}_{harness.charm.app.name}",
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
        "serve": {
            "public": {
                "base_url": "None",
                "cors": {
                    "enabled": True,
                },
            },
        },
    }

    container_config = container.pull(path="/etc/config/kratos.yaml", encoding="utf-8")
    assert yaml.load(container_config.read(), yaml.Loader) == expected_config


def test_kratos_endpoint_info_relation_data_without_ingress_relation_data(
    harness: Harness,
) -> None:
    # set ingress relations without data
    public_ingress_relation_id = harness.add_relation("public-ingress", "public-traefik")
    harness.add_relation_unit(public_ingress_relation_id, "public-traefik/0")
    admin_ingress_relation_id = harness.add_relation("admin-ingress", "admin-traefik")
    harness.add_relation_unit(admin_ingress_relation_id, "admin-traefik/0")

    endpoint_info_relation_id = harness.add_relation(
        "kratos-endpoint-info", "identity-platform-login-ui-operator"
    )
    harness.add_relation_unit(endpoint_info_relation_id, "identity-platform-login-ui-operator/0")

    expected_data = {
        "admin_endpoint": "kratos.kratos-model.svc.cluster.local:4434",
        "public_endpoint": "kratos.kratos-model.svc.cluster.local:4433",
    }

    assert harness.get_relation_data(endpoint_info_relation_id, "kratos") == expected_data


def test_kratos_endpoint_info_relation_data_with_ingress_relation_data(harness: Harness) -> None:
    # set ingress relations with data
    setup_ingress_relation(harness, "public")
    setup_ingress_relation(harness, "admin")

    endpoint_info_relation_id = harness.add_relation(
        "kratos-endpoint-info", "identity-platform-login-ui-operator"
    )
    harness.add_relation_unit(endpoint_info_relation_id, "identity-platform-login-ui-operator/0")

    expected_data = {
        "admin_endpoint": "http://admin:80/kratos-model-kratos",
        "public_endpoint": "http://public:80/kratos-model-kratos",
    }

    assert harness.get_relation_data(endpoint_info_relation_id, "kratos") == expected_data


@pytest.mark.parametrize(
    "action",
    [
        "_on_get_identity_action",
        "_on_delete_identity_action",
        "_on_reset_password_action",
        "_on_create_admin_account_action",
        "_on_run_migration_action",
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


def test_reset_password_action_with_code_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_recover_password_with_code: MagicMock,
) -> None:
    identity_id = mocked_recover_password_with_code.return_value
    event = MagicMock()
    event.params = {"identity-id": identity_id, "recovery-method": "code"}

    harness.charm._on_reset_password_action(event)

    event.set_results.assert_called()


def test_error_on_reset_password_action_with_code_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_recover_password_with_code: MagicMock,
) -> None:
    mocked_recover_password_with_code.side_effect = requests.exceptions.HTTPError()
    event = MagicMock()
    event.params = {"identity-id": "identity_id", "recovery-method": "code"}

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
    event.params = {"identity-id": identity_id, "recovery-method": "code"}

    harness.charm._on_reset_password_action(event)

    event.set_results.assert_called()


def test_reset_password_action_with_link_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_recover_password_with_link: MagicMock,
) -> None:
    identity_id = mocked_recover_password_with_link.return_value
    event = MagicMock()
    event.params = {"identity-id": identity_id, "recovery-method": "link"}

    harness.charm._on_reset_password_action(event)

    event.set_results.assert_called()


def test_error_on_reset_password_action_with_link_with_identity_id(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_recover_password_with_link: MagicMock,
) -> None:
    mocked_recover_password_with_link.side_effect = requests.exceptions.HTTPError()
    event = MagicMock()
    event.params = {"identity-id": "identity_id", "recovery-method": "link"}

    harness.charm._on_reset_password_action(event)

    event.fail.assert_called()


def test_reset_password_action_with_link_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_recover_password_with_link: MagicMock,
) -> None:
    identity_id = mocked_recover_password_with_link.return_value
    event = MagicMock()
    event.params = {"identity-id": identity_id, "recovery-method": "link"}

    harness.charm._on_reset_password_action(event)

    event.set_results.assert_called()


def test_error_on_reset_password_action_with_link_with_email(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_get_identity_from_email: MagicMock,
    mocked_recover_password_with_link: MagicMock,
) -> None:
    mocked_recover_password_with_link.side_effect = requests.exceptions.HTTPError()
    event = MagicMock()
    event.params = {"identity-id": "identity_id", "recovery-method": "link"}

    harness.charm._on_reset_password_action(event)

    event.fail.assert_called()


def test_create_admin_account_with_password(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_create_identity: MagicMock
) -> None:
    identity_id = mocked_create_identity.return_value["id"]
    event = MagicMock()
    event.params = {"username": "username", "password": "p4sSw0rC"}

    harness.charm._on_create_admin_account_action(event)

    event.set_results.assert_called_with({"identity-id": identity_id})


def test_create_admin_account_without_password(
    harness: Harness,
    mocked_kratos_service: MagicMock,
    mocked_create_identity: MagicMock,
    mocked_recover_password_with_link: MagicMock,
) -> None:
    event = MagicMock()
    event.params = {"username": "username"}

    harness.charm._on_create_admin_account_action(event)

    event.set_results.assert_called_with(
        {
            "identity-id": mocked_create_identity.return_value["id"],
            "password-reset-link": mocked_recover_password_with_link.return_value["recovery_link"],
            "expires-at": mocked_recover_password_with_link.return_value["expires_at"],
        }
    )


def test_run_migration(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_run_migration: MagicMock
) -> None:
    event = MagicMock()

    harness.charm._on_run_migration_action(event)

    event.log.assert_called_with("Successfully migrated the database.")


def test_error_on_run_migration(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_run_migration: MagicMock
) -> None:
    mocked_run_migration.return_value = (None, "Error")
    event = MagicMock()

    harness.charm._on_run_migration_action(event)

    event.fail.assert_called()


def test_timeout_on_run_migration(
    harness: Harness, mocked_kratos_service: MagicMock, mocked_run_migration: MagicMock
) -> None:
    mocked_run_migration.side_effect = TimeoutError
    event = MagicMock()

    harness.charm._on_run_migration_action(event)

    event.fail.assert_called()
