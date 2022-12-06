# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import yaml
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus

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


def test_update_container_correct_config(
    harness, mocked_kubernetes_service_patcher, mocked_sql_migration
) -> None:
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
    mocked_sql_migration.assert_called_once()

    assert yaml.safe_load(harness.charm._render_conf_file()) == expected_config


def test_update_container_correct_pebble_layer(
    harness, mocked_kubernetes_service_patcher, mocked_sql_migration
) -> None:

    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)

    initial_plan = harness.get_container_pebble_plan(CONTAINER_NAME)
    assert initial_plan.to_yaml() == "{}\n"

    harness.begin_with_initial_hooks()

    expected_plan = {
        "services": {
            CONTAINER_NAME: {
                "override": "replace",
                "summary": "Kratos Operator layer",
                "startup": "enabled",
                "command": "kratos serve all --config /etc/config/kratos.yaml",
            }
        }
    }
    updated_plan = harness.get_container_pebble_plan(CONTAINER_NAME).to_dict()
    assert expected_plan == updated_plan

    service = harness.model.unit.get_container("kratos").get_service("kratos")
    assert service.is_running()
    assert harness.model.unit.status == ActiveStatus()


def test_cannot_connect_container(harness, mocked_kubernetes_service_patcher) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, False)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.charm.unit.status, WaitingStatus)


def test_missing_database_relation(harness, mocked_kubernetes_service_patcher) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.charm.unit.status, BlockedStatus)


def test_database_not_created(harness, mocked_kubernetes_service_patcher) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)

    db_relation_id = harness.add_relation("pg-database", "postgresql-k8s")
    harness.add_relation_unit(db_relation_id, "postgresql-k8s/0")

    container = harness.model.unit.get_container(CONTAINER_NAME)
    harness.charm.on.kratos_pebble_ready.emit(container)

    assert isinstance(harness.charm.unit.status, WaitingStatus)


def test_on_pebble_ready(
    harness, mocked_kubernetes_service_patcher, mocked_update_container
) -> None:

    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)

    mocked_update_container.assert_called_once()


def test_on_database_created(
    harness, mocked_kubernetes_service_patcher, mocked_update_container
) -> None:
    harness.begin()
    harness.set_can_connect(CONTAINER_NAME, True)
    setup_postgres_relation(harness)

    mocked_update_container.assert_called_once()
