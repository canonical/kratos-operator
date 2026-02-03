#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import http
import json
import logging
from pathlib import Path
from typing import Callable, Optional

import jubilant
import pytest
import requests
from integration.conftest import integrate_dependencies
from integration.constants import (
    ADMIN_EMAIL,
    ADMIN_INGRESS_DOMAIN,
    CA_APP,
    DB_APP,
    IDENTITY_SCHEMA,
    KRATOS_APP,
    KRATOS_IMAGE,
    LOGIN_UI_APP,
    PUBLIC_INGRESS_DOMAIN,
    TRAEFIK_ADMIN_APP,
    TRAEFIK_CHARM,
    TRAEFIK_PUBLIC_APP,
)
from integration.utils import (
    StatusPredicate,
    all_active,
    and_,
    any_error,
    is_blocked,
    remove_integration,
    unit_number,
)

from src.constants import (
    DATABASE_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
)

logger = logging.getLogger(__name__)


@pytest.mark.setup
def test_build_and_deploy(juju: jubilant.Juju, local_charm: Path) -> None:
    juju.deploy(
        str(local_charm),
        resources={"oci-image": KRATOS_IMAGE},
        app=KRATOS_APP,
        trust=True,
    )

    juju.deploy(
        DB_APP,
        channel="14/stable",
        trust=True,
        config={"plugin_pg_trgm_enable": "True", "plugin_btree_gin_enable": "True"},
    )

    juju.deploy(
        CA_APP,
        channel="1/stable",
        trust=True,
    )

    juju.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_PUBLIC_APP,
        channel="latest/edge",
        config={"external_hostname": PUBLIC_INGRESS_DOMAIN},
        trust=True,
    )
    juju.deploy(
        TRAEFIK_CHARM,
        app=TRAEFIK_ADMIN_APP,
        channel="latest/edge",
        config={"external_hostname": ADMIN_INGRESS_DOMAIN},
        trust=True,
    )
    juju.deploy(
        LOGIN_UI_APP,
        channel="latest/edge",
        trust=True,
    )
    juju.integrate(TRAEFIK_PUBLIC_APP, f"{LOGIN_UI_APP}:public-route")
    juju.integrate(f"{TRAEFIK_PUBLIC_APP}:certificates", f"{CA_APP}:certificates")

    # Integrate with dependencies
    integrate_dependencies(juju)

    juju.wait(
        ready=all_active(
            KRATOS_APP,
            DB_APP,
            TRAEFIK_PUBLIC_APP,
            TRAEFIK_ADMIN_APP,
            LOGIN_UI_APP,
        ),
        error=any_error(
            KRATOS_APP,
            DB_APP,
            TRAEFIK_PUBLIC_APP,
            TRAEFIK_ADMIN_APP,
            LOGIN_UI_APP,
        ),
        timeout=15 * 60,
    )


def test_peer_integration(
    leader_peer_integration_data: Optional[dict],
    kratos_version: str,
    migration_key: str,
) -> None:
    assert leader_peer_integration_data
    assert json.loads(leader_peer_integration_data[migration_key]) == kratos_version


def test_login_ui_endpoint_integration(
    leader_login_ui_endpoint_integration_data: Optional[dict],
) -> None:
    assert leader_login_ui_endpoint_integration_data
    assert all(leader_login_ui_endpoint_integration_data.values())


def test_kratos_info_integration(
    leader_kratos_info_integration_data: Optional[dict],
) -> None:
    assert leader_kratos_info_integration_data
    assert all(leader_kratos_info_integration_data.values())


def test_public_route_integration(
    leader_public_route_integration_data: Optional[dict],
    get_webauthn_js: requests.Response,
) -> None:
    assert leader_public_route_integration_data
    assert leader_public_route_integration_data["external_host"] == PUBLIC_INGRESS_DOMAIN
    assert leader_public_route_integration_data["scheme"] == "https"

    assert get_webauthn_js.status_code == http.HTTPStatus.OK


def test_internal_ingress_integration(
    leader_internal_ingress_integration_data: Optional[dict],
    get_identities: requests.Response,
    get_whoami: requests.Response,
) -> None:
    assert leader_internal_ingress_integration_data
    assert leader_internal_ingress_integration_data["external_host"] == ADMIN_INGRESS_DOMAIN
    assert leader_internal_ingress_integration_data["scheme"] == "http"

    assert get_identities.status_code == http.HTTPStatus.OK

    assert get_whoami.status_code == http.HTTPStatus.UNAUTHORIZED


def test_kratos_scale_up(
    juju: jubilant.Juju,
    leader_peer_integration_data: Optional[dict],
    app_integration_data: Callable,
) -> None:
    target_unit_number = 2
    juju.cli("scale-application", KRATOS_APP, str(target_unit_number))

    juju.wait(
        ready=and_(
            all_active(KRATOS_APP),
            unit_number(KRATOS_APP, target_unit_number),
        ),
        error=any_error(KRATOS_APP),
        timeout=5 * 60,
    )

    follower_peer_data = app_integration_data(KRATOS_APP, PEER_INTEGRATION_NAME, 1)
    assert follower_peer_data
    assert leader_peer_integration_data == follower_peer_data


def test_create_admin_account_action(
    juju: jubilant.Juju,
    admin_password_secret: str,
) -> None:
    res = juju.run(
        f"{KRATOS_APP}/0",
        "create-admin-account",
        params={
            "username": "admin",
            "email": ADMIN_EMAIL,
            "name": "Admin Admin",
            "phone_number": "6912345678",
            "password-secret-id": admin_password_secret,
        },
    )

    assert res.results["identity-id"]


def test_get_identity_action_by_email(
    juju: jubilant.Juju,
    request: pytest.FixtureRequest,
) -> None:
    res = juju.run(
        f"{KRATOS_APP}/0",
        "get-identity",
        params={"email": ADMIN_EMAIL},
    )

    assert res.results["id"]
    request.config.cache.set("identity-id", res.results["id"])


def test_get_identity_action_by_id(juju: jubilant.Juju, request: pytest.FixtureRequest) -> None:
    res = juju.run(
        f"{KRATOS_APP}/0",
        "get-identity",
        params={"identity-id": request.config.cache.get("identity-id", "")},
    )

    assert res.results["traits"]["email"] == ADMIN_EMAIL


def test_reset_password_action(
    juju: jubilant.Juju,
    new_admin_password_secret: str,
    request: pytest.FixtureRequest,
) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    res = juju.run(
        f"{KRATOS_APP}/0",
        "reset-password",
        params={
            "identity-id": identity_id,
            "password-secret-id": new_admin_password_secret,
        },
    )

    assert res.results["id"] == identity_id


def test_reset_password_action_with_recovery_code(
    juju: jubilant.Juju, request: pytest.FixtureRequest
) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    res = juju.run(f"{KRATOS_APP}/0", "reset-password", params={"identity-id": identity_id})

    assert res.results["recovery-link"]
    assert res.results["recovery-code"]


def test_list_oidc_accounts(juju: jubilant.Juju, request: pytest.FixtureRequest) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    res = juju.run(f"{KRATOS_APP}/0", "list-oidc-accounts", params={"identity-id": identity_id})

    assert res.status == "completed"


def test_reset_identity_mfa_action(juju: jubilant.Juju, request: pytest.FixtureRequest) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    res = juju.run(
        f"{KRATOS_APP}/0",
        "reset-identity-mfa",
        params={
            "identity-id": identity_id,
            "mfa-type": "webauthn",
        },
    )

    assert res.status == "completed"


def test_unlink_oidc_account(juju: jubilant.Juju, request: pytest.FixtureRequest) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    res = juju.run(
        f"{KRATOS_APP}/0",
        "unlink-oidc-account",
        params={
            "identity-id": identity_id,
            "credential-id": "credential-id",
        },
    )

    assert res.status == "completed"


def test_invalidate_identity_sessions_action(
    juju: jubilant.Juju, request: pytest.FixtureRequest
) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    res = juju.run(
        f"{KRATOS_APP}/0",
        "invalidate-identity-sessions",
        params={"identity-id": identity_id},
    )

    assert res.status == "completed"


def test_delete_identity_action(juju: jubilant.Juju, request: pytest.FixtureRequest) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    res = juju.run(
        f"{KRATOS_APP}/0",
        "delete-identity",
        params={"identity-id": identity_id},
    )

    assert res.status == "completed"

    # Verify deletion
    with pytest.raises(jubilant.TaskError, match="Identity not found"):
        juju.run(
            f"{KRATOS_APP}/0",
            "get-identity",
            params={"identity-id": identity_id},
        )


def test_identity_schemas_config(
    juju: jubilant.Juju,
    get_identity_schemas: Callable[[], requests.Response],
) -> None:
    original_schemas = get_identity_schemas().json()

    schema_id = "user_v1"
    juju.config(
        KRATOS_APP,
        {
            "identity_schemas": json.dumps({schema_id: IDENTITY_SCHEMA}),
            "default_identity_schema_id": schema_id,
        },
    )

    juju.wait(
        ready=and_(
            all_active(KRATOS_APP),
        ),
        error=any_error(KRATOS_APP),
        timeout=5 * 60,
    )

    identity_schemas = get_identity_schemas().json()
    assert len(identity_schemas) == 1
    assert identity_schemas[0]["id"] == schema_id

    # Reset config
    juju.config(
        KRATOS_APP,
        {
            "identity_schemas": "",
            "default_identity_schema_id": "",
        },
    )

    juju.wait(
        ready=and_(
            all_active(KRATOS_APP),
        ),
        error=any_error(KRATOS_APP),
        timeout=5 * 60,
    )

    identity_schemas = get_identity_schemas().json()

    assert all(schema in original_schemas for schema in identity_schemas)
    assert len(identity_schemas) == len(original_schemas)


@pytest.mark.parametrize(
    "remote_app_name,integration_name,is_status",
    [
        (DB_APP, DATABASE_INTEGRATION_NAME, is_blocked),
        (TRAEFIK_PUBLIC_APP, PUBLIC_ROUTE_INTEGRATION_NAME, all_active),
        (LOGIN_UI_APP, LOGIN_UI_INTEGRATION_NAME, all_active),
    ],
)
def test_remove_integration(
    juju: jubilant.Juju,
    remote_app_name: str,
    integration_name: str,
    is_status: Callable[[str], StatusPredicate],
) -> None:
    """Test removing and re-adding integration."""
    with remove_integration(juju, remote_app_name, integration_name):
        juju.wait(
            ready=is_status(KRATOS_APP),
            error=any_error(KRATOS_APP),
            timeout=10 * 60,
        )
    juju.wait(
        ready=all_active(KRATOS_APP, remote_app_name),
        error=any_error(KRATOS_APP, remote_app_name),
        timeout=10 * 60,
    )


def test_kratos_scale_down(
    juju: jubilant.Juju,
) -> None:
    target_unit_num = 1
    juju.cli("scale-application", KRATOS_APP, str(target_unit_num))

    juju.wait(
        ready=and_(
            all_active(KRATOS_APP),
            unit_number(KRATOS_APP, target_unit_num),
        ),
        error=any_error(KRATOS_APP),
        timeout=5 * 60,
    )


@pytest.mark.teardown
def test_remove_application(juju: jubilant.Juju) -> None:
    """Test removing the application."""
    juju.remove_application(KRATOS_APP, destroy_storage=True)
    juju.wait(lambda s: KRATOS_APP not in s.apps, timeout=1000)
