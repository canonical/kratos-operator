#!/usr/bin/env python3
# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import http
import json
import logging
from pathlib import Path
from typing import Awaitable, Callable, Optional

import pytest
from conftest import (
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
    integrate_dependencies,
)
from httpx import Response
from juju.application import Application
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

from constants import PEER_INTEGRATION_NAME

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, local_charm: str | Path) -> None:
    await ops_test.model.deploy(
        entity_url=str(local_charm),
        resources={"oci-image": KRATOS_IMAGE},
        application_name=KRATOS_APP,
        trust=True,
        series="jammy",
    )

    await ops_test.model.deploy(
        DB_APP,
        channel="14/stable",
        trust=True,
        config={"plugin_pg_trgm_enable": "True", "plugin_btree_gin_enable": "True"},
    )

    await ops_test.model.deploy(
        CA_APP,
        channel="1/stable",
        trust=True,
    )

    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_PUBLIC_APP,
        channel="latest/edge",
        config={"external_hostname": PUBLIC_INGRESS_DOMAIN},
        trust=True,
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_ADMIN_APP,
        channel="latest/edge",
        config={"external_hostname": ADMIN_INGRESS_DOMAIN},
        trust=True,
    )
    await ops_test.model.deploy(
        LOGIN_UI_APP,
        channel="latest/edge",
        trust=True,
    )
    await ops_test.model.integrate(TRAEFIK_PUBLIC_APP, f"{LOGIN_UI_APP}:public-route")
    await ops_test.model.integrate(f"{TRAEFIK_PUBLIC_APP}:certificates", f"{CA_APP}:certificates")

    # Integrate with dependencies
    await integrate_dependencies(ops_test)

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP, DB_APP, TRAEFIK_PUBLIC_APP, TRAEFIK_ADMIN_APP, LOGIN_UI_APP],
        status="active",
        raise_on_blocked=False,
        raise_on_error=False,
        timeout=5 * 60,
    )


async def test_peer_integration(
    leader_peer_integration_data: Optional[dict],
    kratos_version: str,
    migration_key: str,
) -> None:
    assert leader_peer_integration_data
    assert json.loads(leader_peer_integration_data[migration_key]) == kratos_version


async def test_login_ui_endpoint_integration(
    leader_login_ui_endpoint_integration_data: Optional[dict],
) -> None:
    assert leader_login_ui_endpoint_integration_data
    assert all(leader_login_ui_endpoint_integration_data.values())


async def test_kratos_info_integration(
    leader_kratos_info_integration_data: Optional[dict],
) -> None:
    assert leader_kratos_info_integration_data
    assert all(leader_kratos_info_integration_data.values())


async def test_public_route_integration(
    ops_test: OpsTest,
    leader_public_route_integration_data: Optional[dict],
    get_webauthn_js: Response,
) -> None:
    assert leader_public_route_integration_data
    assert leader_public_route_integration_data["external_host"] == PUBLIC_INGRESS_DOMAIN
    assert leader_public_route_integration_data["scheme"] == "https"

    assert get_webauthn_js.status_code == http.HTTPStatus.OK


async def test_internal_ingress_integration(
    leader_internal_ingress_integration_data: Optional[dict],
    get_identities: Response,
    get_whoami: Response,
) -> None:
    assert leader_internal_ingress_integration_data
    assert leader_internal_ingress_integration_data["external_host"] == ADMIN_INGRESS_DOMAIN
    assert leader_internal_ingress_integration_data["scheme"] == "http"

    # examine the admin endpoint
    assert get_identities.status_code == http.HTTPStatus.OK

    # examine the public endpoint
    assert get_whoami.status_code == http.HTTPStatus.UNAUTHORIZED


@pytest.mark.abort_on_fail
async def test_create_admin_account_action(
    kratos_unit: Unit,
    admin_password_secret: str,
    request: pytest.FixtureRequest,
) -> None:
    action = await kratos_unit.run_action(
        "create-admin-account",
        **{
            "username": "admin",
            "email": ADMIN_EMAIL,
            "name": "Admin Admin",
            "phone_number": "6912345678",
            "password-secret-id": admin_password_secret,
        },
    )
    res = (await action.wait()).results

    assert res["identity-id"]

    request.config.cache.set("identity-id", res["identity-id"])


async def test_get_identity_action_by_email(kratos_unit: Unit) -> None:
    action = await kratos_unit.run_action(
        "get-identity",
        email=ADMIN_EMAIL,
    )

    res = (await action.wait()).results

    assert res["id"]


async def test_get_identity_action_by_id(
    kratos_unit: Unit, request: pytest.FixtureRequest
) -> None:
    action = await kratos_unit.run_action(
        "get-identity",
        **{"identity-id": request.config.cache.get("identity-id", "")},
    )

    res = (await action.wait()).results

    assert res["traits"]["email"] == ADMIN_EMAIL


async def test_reset_password_action(
    kratos_unit: Unit,
    new_admin_password_secret: str,
    request: pytest.FixtureRequest,
) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    action = await kratos_unit.run_action(
        "reset-password",
        **{
            "identity-id": identity_id,
            "password-secret-id": new_admin_password_secret,
        },
    )

    res = (await action.wait()).results

    assert res["id"] == identity_id


async def test_reset_password_action_with_recovery_code(
    kratos_unit: Unit, request: pytest.FixtureRequest
) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    action = await kratos_unit.run_action("reset-password", **{"identity-id": identity_id})

    res = (await action.wait()).results

    assert res["recovery-link"]
    assert res["recovery-code"]


async def test_list_oidc_accounts(kratos_unit: Unit, request: pytest.FixtureRequest) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    action = await kratos_unit.run_action("list-oidc-accounts", **{"identity-id": identity_id})

    res = await action.wait()

    assert res.status == "completed"


async def test_reset_identity_mfa_action(
    kratos_unit: Unit, request: pytest.FixtureRequest
) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    action = await kratos_unit.run_action(
        "reset-identity-mfa",
        **{
            "identity-id": identity_id,
            "mfa-type": "webauthn",
        },
    )

    res = await action.wait()

    assert res.status == "completed"


async def test_unlink_oidc_account(kratos_unit: Unit, request: pytest.FixtureRequest) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    action = await kratos_unit.run_action(
        "unlink-oidc-account",
        **{
            "identity-id": identity_id,
            "credential-id": "credential-id",
        },
    )

    res = await action.wait()

    assert res.status == "completed"


async def test_invalidate_identity_sessions_action(
    kratos_unit: Unit, request: pytest.FixtureRequest
) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    action = await kratos_unit.run_action(
        "invalidate-identity-sessions",
        **{"identity-id": identity_id},
    )

    res = await action.wait()

    assert res.status == "completed"


async def test_delete_identity_action(kratos_unit: Unit, request: pytest.FixtureRequest) -> None:
    identity_id = request.config.cache.get("identity-id", "")

    action = await kratos_unit.run_action(
        "delete-identity",
        **{"identity-id": identity_id},
    )

    res = await action.wait()
    assert res.status == "completed"

    action = await kratos_unit.run_action(
        "get-identity",
        **{"identity-id": identity_id},
    )

    res = await action.wait()
    assert res.message == "Identity not found"


async def test_identity_schemas_config(
    ops_test: OpsTest,
    get_identity_schemas: Callable[[], Awaitable[Response]],
    kratos_application: Application,
) -> None:
    original_schemas = (await get_identity_schemas()).json()

    schema_id = "user_v1"
    await kratos_application.set_config({
        "identity_schemas": json.dumps({schema_id: IDENTITY_SCHEMA}),
        "default_identity_schema_id": schema_id,
    })
    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=5 * 60,
    )

    identity_schemas = (await get_identity_schemas()).json()
    assert len(identity_schemas) == 1
    assert identity_schemas[0]["id"] == schema_id

    await kratos_application.set_config({
        "identity_schemas": "",
        "default_identity_schema_id": "",
    })

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=5 * 60,
    )

    identity_schemas = (await get_identity_schemas()).json()

    assert all(schema in original_schemas for schema in identity_schemas)
    assert len(identity_schemas) == len(original_schemas)


async def test_kratos_scale_up(
    ops_test: OpsTest,
    kratos_application: Application,
    leader_peer_integration_data: Optional[dict],
    app_integration_data: Callable,
) -> None:
    target_unit_number = 2
    await kratos_application.scale(target_unit_number)

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=False,
        timeout=5 * 60,
        wait_for_exact_units=target_unit_number,
    )

    follower_peer_data = await app_integration_data(KRATOS_APP, PEER_INTEGRATION_NAME, 1)
    assert follower_peer_data
    assert leader_peer_integration_data == follower_peer_data


async def test_kratos_scale_down(
    ops_test: OpsTest,
    kratos_application: Application,
) -> None:
    target_unit_num = 1
    await kratos_application.scale(target_unit_num)

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        timeout=5 * 60,
        wait_for_exact_units=target_unit_num,
    )
