# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json

import pytest
import yaml
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

from charm import DB_MIGRATE_VERSION, PEER_KEY_DB_MIGRATE_VERSION

CONTAINER_NAME = "kratos"
DB_USERNAME = "fake_relation_id_1"
DB_PASSWORD = "fake-password"
DB_ENDPOINTS = "postgresql-k8s-primary.namespace.svc.cluster.local:5432"


def setup_postgres_relation(harness):
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


def setup_ingress_relation(harness, type):
    relation_id = harness.add_relation(f"{type}-ingress", f"{type}-traefik")
    harness.add_relation_unit(relation_id, f"{type}-traefik/0")
    harness.update_relation_data(
        relation_id,
        f"{type}-traefik",
        {"ingress": json.dumps({"url": f"http://{type}:80/{harness.model.name}-kratos"})},
    )
    return relation_id


def setup_peer_relation(harness):
    rel_id = harness.add_relation("kratos-peers", "kratos")
    harness.add_relation_unit(rel_id, "kratos/1")
    harness.update_relation_data(
        rel_id,
        "kratos",
        {PEER_KEY_DB_MIGRATE_VERSION: DB_MIGRATE_VERSION},
    )


def setup_hydra_relation(harness) -> int:
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


def setup_login_ui_relation(harness) -> int:
    relation_id = harness.add_relation("ui-endpoint-info", "identity-platform-login-ui-operator")
    harness.add_relation_unit(relation_id, "identity-platform-login-ui-operator/0")
    endpoint = f"http://public:80/{harness.model.name}-identity-platform-login-ui-operator"
    harness.update_relation_data(
        relation_id,
        "identity-platform-login-ui-operator",
        {
            "consent_url": f"{endpoint}/consent",
            "error_url": f"{endpoint}/error",
            "index_url": f"{endpoint}/index",
            "login_url": f"{endpoint}/login",
            "oidc_error_url": f"{endpoint}/oidc_error",
            "registration_url": f"{endpoint}/registration",
            "default_url": endpoint,
        },
    )
    return relation_id


def trigger_database_changed(harness) -> None:
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


def setup_external_provider_relation(harness):
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


def test_on_pebble_ready_cannot_connect_container(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, WaitingStatus)


def test_on_pebble_ready_correct_plan(harness) -> None:
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


def test_on_pebble_ready_correct_plan_with_dev_flag(harness, caplog) -> None:
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


def test_on_pebble_ready_service_not_started_when_database_not_created(harness) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert not service.is_running()


def test_on_pebble_ready_service_started_when_database_is_created(harness) -> None:
    setup_postgres_relation(harness)
    setup_peer_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert harness.model.unit.status == ActiveStatus()


def test_on_pebble_ready_has_correct_config_when_database_is_created(harness) -> None:
    setup_postgres_relation(harness)
    login_relation_id = setup_login_ui_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "default",
            "schemas": [
                {"id": "default", "url": "file:///etc/config/identity.default.schema.json"}
            ],
        },
        "selfservice": {
            "default_browser_return_url": harness.get_relation_data(
                login_relation_id, "identity-platform-login-ui-operator"
            )["default_url"],
            "flows": {
                "error": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["error_url"],
                },
                "login": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["login_url"],
                },
                "registration": {
                    "enabled": True,
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["registration_url"],
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


def test_on_pebble_ready_when_missing_database_relation(harness) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, BlockedStatus)
    assert "Missing postgres database relation" in harness.charm.unit.status.message


def test_on_pebble_ready_when_database_not_created_yet(harness) -> None:
    trigger_database_changed(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.model.unit.status, WaitingStatus)
    assert "Waiting for database creation" in harness.charm.unit.status.message


def test_on_database_created_cannot_connect_container(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)

    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_database_created_when_pebble_is_not_ready(harness, mocked_pebble_exec_success) -> None:
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for Kratos service" in harness.charm.unit.status.message
    mocked_pebble_exec_success.assert_not_called()


def test_on_database_created_when_pebble_is_ready_in_leader_unit_missing_peer_relation(
    harness,
) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for peer relation" in harness.charm.unit.status.message


def test_on_database_created_updated_config_and_start_service_when_pebble_is_ready_in_leader_unit(
    harness, mocked_pebble_exec_success
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
    harness,
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
    harness, mocked_pebble_exec
) -> None:
    harness.set_leader(False)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_postgres_relation(harness)

    mocked_pebble_exec.assert_not_called()


def test_on_database_created_pending_migration_in_non_leader_unit(harness):
    harness.set_leader(False)
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    rel_id = harness.add_relation("kratos-peers", "kratos")
    harness.add_relation_unit(rel_id, "kratos/1")

    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for database migration to complete" in harness.charm.unit.status.message


def test_on_database_created_when_migration_is_successful(
    harness, mocked_pebble_exec_success
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


def test_on_database_created_when_migration_failed(harness, mocked_pebble_exec_failed) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)
    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, BlockedStatus)


def test_on_database_changed_cannot_connect_container(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_database_changed_when_pebble_is_not_ready(harness) -> None:
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for Kratos service" in harness.charm.unit.status.message


def test_on_database_changed_when_pebble_is_ready(harness, mocked_pebble_exec_success) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    updated_config = yaml.safe_load(harness.charm._render_conf_file())
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert isinstance(harness.charm.unit.status, ActiveStatus)


def test_on_config_changed_cannot_connect_container(harness) -> None:
    harness.set_can_connect(CONTAINER_NAME, False)
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting to connect to Kratos container" in harness.charm.unit.status.message


def test_on_config_changed_when_pebble_is_not_ready(harness) -> None:
    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    assert "Waiting for Kratos service" in harness.charm.unit.status.message


def test_on_config_changed_when_pebble_is_ready(harness, mocked_pebble_exec_success) -> None:
    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_peer_relation(harness)
    setup_postgres_relation(harness)

    updated_config = yaml.safe_load(harness.charm._render_conf_file())
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert isinstance(harness.charm.unit.status, ActiveStatus)


@pytest.mark.parametrize("api_type,port", [("admin", "4434"), ("public", "4433")])
def test_ingress_relation_created(harness, mocked_fqdn, api_type, port) -> None:
    relation_id = setup_ingress_relation(harness, api_type)
    app_data = harness.get_relation_data(relation_id, harness.charm.app)

    assert app_data == {
        "host": mocked_fqdn.return_value,
        "model": harness.model.name,
        "name": "kratos",
        "port": port,
        "strip-prefix": "true",
    }


def test_on_client_config_changed_when_no_dns_available(harness) -> None:
    setup_postgres_relation(harness)
    setup_external_provider_relation(harness)

    assert isinstance(harness.charm.unit.status, BlockedStatus)


def test_on_client_config_changed_with_ingress(harness, mocked_container) -> None:
    setup_postgres_relation(harness)
    setup_ingress_relation(harness, "public")
    login_relation_id = setup_login_ui_relation(harness)
    relation_id = setup_external_provider_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "default",
            "schemas": [
                {"id": "default", "url": "file:///etc/config/identity.default.schema.json"}
            ],
        },
        "selfservice": {
            "default_browser_return_url": harness.get_relation_data(
                login_relation_id, "identity-platform-login-ui-operator"
            )["default_url"],
            "flows": {
                "error": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["error_url"],
                },
                "login": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["login_url"],
                },
                "registration": {
                    "enabled": True,
                    "after": {"oidc": {"hooks": [{"hook": "session"}]}},
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["registration_url"],
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


def test_on_client_config_changed_with_external_url_config(harness, mocked_container) -> None:
    # This is the provider id that will be computed based on the provider config
    provider_id = "generic_9d07bcc95549089d7f16120e8bed5396469a5426"
    harness.update_config({"external_url": "https://example.com"})
    setup_postgres_relation(harness)
    login_relation_id = setup_login_ui_relation(harness)
    relation_id = setup_external_provider_relation(harness)
    container = harness.model.unit.get_container(CONTAINER_NAME)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "default",
            "schemas": [
                {"id": "default", "url": "file:///etc/config/identity.default.schema.json"}
            ],
        },
        "selfservice": {
            "default_browser_return_url": harness.get_relation_data(
                login_relation_id, "identity-platform-login-ui-operator"
            )["default_url"],
            "flows": {
                "error": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["error_url"],
                },
                "login": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["login_url"],
                },
                "registration": {
                    "enabled": True,
                    "after": {"oidc": {"hooks": [{"hook": "session"}]}},
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["registration_url"],
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


def test_on_client_config_changed_with_hydra(harness) -> None:
    setup_postgres_relation(harness)
    login_relation_id = setup_login_ui_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_hydra_relation(harness)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "default",
            "schemas": [
                {"id": "default", "url": "file:///etc/config/identity.default.schema.json"}
            ],
        },
        "selfservice": {
            "default_browser_return_url": harness.get_relation_data(
                login_relation_id, "identity-platform-login-ui-operator"
            )["default_url"],
            "flows": {
                "error": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["error_url"],
                },
                "login": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["login_url"],
                },
                "registration": {
                    "enabled": True,
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["registration_url"],
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


def test_on_client_config_changed_when_missing_hydra_relation_data(harness) -> None:
    setup_postgres_relation(harness)
    setup_peer_relation(harness)
    login_relation_id = setup_login_ui_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    relation_id = harness.add_relation("endpoint-info", "hydra")
    harness.add_relation_unit(relation_id, "hydra/0")

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "default",
            "schemas": [
                {"id": "default", "url": "file:///etc/config/identity.default.schema.json"}
            ],
        },
        "selfservice": {
            "default_browser_return_url": harness.get_relation_data(
                login_relation_id, "identity-platform-login-ui-operator"
            )["default_url"],
            "flows": {
                "error": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["error_url"],
                },
                "login": {
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["login_url"],
                },
                "registration": {
                    "enabled": True,
                    "ui_url": harness.get_relation_data(
                        login_relation_id, "identity-platform-login-ui-operator"
                    )["registration_url"],
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


def test_kratos_endpoint_info_relation_data_without_ingress_relation_data(harness) -> None:
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


def test_kratos_endpoint_info_relation_data_with_ingress_relation_data(harness) -> None:
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


def test_on_client_config_changed_without_login_ui_endpoints(harness) -> None:
    setup_postgres_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_hydra_relation(harness)

    login_ui_relation_id = harness.add_relation(
        "ui-endpoint-info", "identity-platform-login-ui-operator"
    )
    harness.add_relation_unit(login_ui_relation_id, "identity-platform-login-ui-operator/0")

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "default",
            "schemas": [
                {"id": "default", "url": "file:///etc/config/identity.default.schema.json"}
            ],
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


def test_on_client_config_changed_when_missing_login_ui_and_hydra_relation_data(harness) -> None:
    setup_postgres_relation(harness)
    setup_peer_relation(harness)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    relation_id = harness.add_relation("endpoint-info", "hydra")
    harness.add_relation_unit(relation_id, "hydra/0")

    login_ui_relation_id = harness.add_relation(
        "ui-endpoint-info", "identity-platform-login-ui-operator"
    )
    harness.add_relation_unit(login_ui_relation_id, "identity-platform-login-ui-operator/0")

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "default",
            "schemas": [
                {"id": "default", "url": "file:///etc/config/identity.default.schema.json"}
            ],
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
