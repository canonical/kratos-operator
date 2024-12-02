#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import http
import json
import logging
from asyncio import sleep
from typing import Awaitable, Callable, Optional, Tuple

import pytest
from httpx import AsyncClient, Response
from pytest_operator.plugin import OpsTest

from conftest import (
    ADMIN_MAIL,
    CA_APP,
    DB_APP,
    IDENTITY_SCHEMA,
    ISTIO_CONTROL_PLANE_CHARM,
    ISTIO_INGRESS_CHARM,
    KRATOS_APP,
    KRATOS_IMAGE,
    PUBLIC_INGRESS_APP,
    PUBLIC_INGRESS_DOMAIN,
)

logger = logging.getLogger(__name__)


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    await ops_test.track_model(
        alias="istio-system",
        model_name="istio-system",
        destroy_storage=True,
    )
    istio_system = ops_test.models.get("istio-system")

    await istio_system.model.deploy(
        application_name=ISTIO_CONTROL_PLANE_CHARM,
        entity_url=ISTIO_CONTROL_PLANE_CHARM,
        channel="latest/edge",
        trust=True,
    )
    await istio_system.model.wait_for_idle(
        [ISTIO_CONTROL_PLANE_CHARM],
        status="active",
        timeout=5 * 60,
    )

    charm = await ops_test.build_charm(".")

    await ops_test.model.deploy(
        "postgresql-k8s",
        channel="14/stable",
        trust=True,
        config={"plugin_pg_trgm_enable": "True", "plugin_btree_gin_enable": "True"},
    )

    await ops_test.model.deploy(
        ISTIO_INGRESS_CHARM,
        application_name=PUBLIC_INGRESS_APP,
        trust=True,
        channel="latest/edge",
        config={"external_hostname": "public"},
    )

    await ops_test.model.deploy(
        CA_APP,
        channel="latest/stable",
        trust=True,
    )

    await ops_test.model.deploy(
        str(charm),
        resources={"oci-image": KRATOS_IMAGE},
        application_name=KRATOS_APP,
        trust=True,
        series="jammy",
    )

    await ops_test.model.integrate(f"{PUBLIC_INGRESS_APP}:certificates", f"{CA_APP}:certificates")
    await ops_test.model.integrate(KRATOS_APP, DB_APP)
    await ops_test.model.integrate(f"{KRATOS_APP}:public-ingress", PUBLIC_INGRESS_APP)

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP, PUBLIC_INGRESS_APP, DB_APP],
        status="active",
        raise_on_blocked=False,
        raise_on_error=False,
        timeout=5 * 60,
    )


async def test_public_ingress_integration(
    ops_test: OpsTest,
    leader_public_ingress_integration_data: Optional[dict],
    public_ingress_address: str,
    http_client: AsyncClient,
) -> None:
    assert leader_public_ingress_integration_data
    assert leader_public_ingress_integration_data["ingress"]

    data = json.loads(leader_public_ingress_integration_data["ingress"])
    assert data["url"] == f"https://{PUBLIC_INGRESS_DOMAIN}/{ops_test.model_name}-{KRATOS_APP}"

    # Test HTTP to HTTPS redirection
    http_endpoint = f"http://{public_ingress_address}/{ops_test.model_name}-{KRATOS_APP}/.well-known/ory/webauthn.js"
    resp = await http_client.get(
        http_endpoint,
        headers={"Host": PUBLIC_INGRESS_DOMAIN},
    )
    assert resp.status_code == http.HTTPStatus.MOVED_PERMANENTLY, (
        f"Expected HTTP 301 for {http_endpoint}, got {resp.status_code}."
    )

    # Test HTTPS endpoint
    https_endpoint = f"https://{public_ingress_address}/{ops_test.model_name}-{KRATOS_APP}/.well-known/ory/webauthn.js"
    resp = await http_client.get(
        https_endpoint,
        headers={"Host": PUBLIC_INGRESS_DOMAIN},
        extensions={"sni_hostname": PUBLIC_INGRESS_DOMAIN},
    )
    assert resp.status_code == http.HTTPStatus.OK, (
        f"Expected HTTP 200 for {https_endpoint}, got {resp.status_code}."
    )


@pytest.mark.abort_on_fail
async def test_create_admin_account(ops_test: OpsTest, password_secret: Tuple[str, str]) -> None:
    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "create-admin-account",
            **{
                "username": "admin",
                "email": ADMIN_MAIL,
                "name": "Admin Admin",
                "phone_number": "6912345678",
                "password-secret-id": password_secret[0],
            },
        )
    )

    res = await action.wait()
    print(res)
    print(res.results)

    assert "identity-id" in res.results


async def test_get_identity(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "get-identity",
            email=ADMIN_MAIL,
        )
    )

    res = (await action.wait()).results

    assert res["id"]


async def test_reset_password(ops_test: OpsTest) -> None:
    secret_name = "password-secret"
    secret_id = await ops_test.model.add_secret(
        name=secret_name, data_args=["password=some-password"]
    )
    await ops_test.model.grant_secret(secret_name=secret_name, application=KRATOS_APP)

    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "reset-password",
            **{
                "email": ADMIN_MAIL,
                "password-secret-id": secret_id,
            },
        )
    )

    action_output = await action.wait()

    assert "id" in action_output.results
    assert action_output.status == "completed"


async def test_reset_password_with_recovery_code(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "reset-password",
            email=ADMIN_MAIL,
        )
    )

    action_output = await action.wait()

    assert "recovery-link" in action_output.results
    assert action_output.status == "completed"


async def test_reset_identity_mfa(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "reset-identity-mfa",
            **{
                "email": ADMIN_MAIL,
                "mfa-type": "totp",
            },
        )
    )

    action_output = await action.wait()

    assert action_output.status == "completed"


async def test_invalidate_identity_sessions(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "invalidate-identity-sessions",
            email=ADMIN_MAIL,
        )
    )

    action_output = await action.wait()

    assert action_output.status == "completed"


async def test_delete_identity(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "get-identity",
            email=ADMIN_MAIL,
        )
    )

    res = (await action.wait()).results

    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "delete-identity",
            **{
                "identity-id": res["id"],
            },
        )
    )

    await action.wait()

    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "get-identity",
            email=ADMIN_MAIL,
        )
    )
    res = await action.wait()

    assert res.message == "Couldn't retrieve identity_id from email."


async def test_identity_schemas_config(
    ops_test: OpsTest,
    public_ingress_address: str,
    http_client: AsyncClient,
    get_schemas: Callable[[], Awaitable[Response]],
) -> None:
    # Get the original identity schemas
    resp = await get_schemas()
    original_resp = resp.json()

    # Apply the new identity schema
    schema_id = "user_v1"
    await ops_test.model.applications[KRATOS_APP].set_config({
        "identity_schemas": json.dumps({schema_id: IDENTITY_SCHEMA}),
        "default_identity_schema_id": schema_id,
    })

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=5 * 60,
    )

    # Verify the schema update
    for _ in range(40):
        resp = await get_schemas()
        if len(resp.json()) == 1:
            break
        await sleep(3)
    else:
        raise TimeoutError("Timed out waiting for the schemas to update.")

    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == schema_id

    # Reset the identity schema
    await ops_test.model.applications[KRATOS_APP].set_config({
        "identity_schemas": "",
        "default_identity_schema_id": "",
    })

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=5 * 60,
    )

    # Verify the schema reset
    for _ in range(40):
        resp = await get_schemas()
        if len(resp.json()) == 2:
            break
        await sleep(3)
    else:
        raise TimeoutError("Timed out waiting for the schemas to update.")

    assert all(s in original_resp for s in resp.json())
    assert len(original_resp) == len(resp.json())


async def test_kratos_scale_up(ops_test: OpsTest) -> None:
    app = ops_test.model.applications[KRATOS_APP]

    await app.scale(3)

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
        wait_for_exact_units=3,
    )


async def test_kratos_scale_down(ops_test: OpsTest) -> None:
    app = ops_test.model.applications[KRATOS_APP]

    await app.scale(1)

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        timeout=1000,
    )
