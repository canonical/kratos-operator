# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import yaml
from ops.model import ActiveStatus, WaitingStatus

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


def test_correct_config(harness, mocked_kubernetes_service_patcher, mocked_sql_migration) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)

    expected_config = {
        "log": {"level": "trace"},
        "identity": {
            "default_schema_id": "default",
            "schemas": [
                {"id": "default", "url": "file:///etc/config/identity.default.schema.json"}
            ],
        },
        "selfservice": {
            "default_browser_return_url": "http://127.0.0.1:9999/",
            "flows": {
                "registration": {
                    "enabled": True,
                    "ui_url": "http://127.0.0.1:9999/registration",
                }
            },
        },
        "dsn": f"postgres://{DB_USERNAME}:{DB_PASSWORD}@{DB_ENDPOINTS}/postgres",
        "courier": {
            "smtp": {"connection_uri": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true"}
        },
    }

    assert yaml.safe_load(harness.charm._config) == expected_config


def test_on_pebble_layer(harness, mocked_kubernetes_service_patcher, mocked_sql_migration) -> None:

    harness.set_can_connect(CONTAINER_NAME, True)

    initial_plan = harness.get_container_pebble_plan(CONTAINER_NAME)
    assert initial_plan.to_yaml() == "{}\n"

    harness.begin()

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

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert not service.is_running()
    assert harness.model.unit.status == ActiveStatus()


def test_on_database_created_cannot_connect_container(
    harness, mocked_kubernetes_service_patcher
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, False)

    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)


def test_on_database_created_before_pebble_ready(
    harness, mocked_kubernetes_service_patcher, mocked_sql_migration
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)
    mocked_sql_migration.assert_not_called()


def test_on_database_created_after_pebble_ready(
    harness, mocked_kubernetes_service_patcher, mocked_sql_migration
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    setup_postgres_relation(harness)

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert isinstance(harness.charm.unit.status, ActiveStatus)
    mocked_sql_migration.assert_called_once()

    updated_config = yaml.safe_load(harness.charm._config)
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert DB_PASSWORD in updated_config["dsn"]
    assert DB_USERNAME in updated_config["dsn"]


def test_on_database_changed_cannot_connect_container(
    harness, mocked_kubernetes_service_patcher
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, False)

    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)


def test_on_database_changed_before_pebble_ready(
    harness, mocked_kubernetes_service_patcher
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    trigger_database_changed(harness)

    assert isinstance(harness.charm.unit.status, WaitingStatus)


def test_on_database_changed_after_pebble_ready(
    harness, mocked_kubernetes_service_patcher, mocked_sql_migration
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    trigger_database_changed(harness)

    updated_config = yaml.safe_load(harness.charm._config)
    assert DB_ENDPOINTS in updated_config["dsn"]
    assert isinstance(harness.charm.unit.status, ActiveStatus)
