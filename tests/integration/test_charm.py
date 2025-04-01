#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from asyncio import sleep
from pathlib import Path
from typing import Tuple

import pytest
import requests
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
KRATOS_APP = METADATA["name"]
DB_APP = "postgresql-k8s"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_ADMIN_APP = "traefik-admin"
TRAEFIK_PUBLIC_APP = "traefik-public"
ADMIN_MAIL = "admin1@adminmail.com"
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


async def get_unit_address(ops_test: OpsTest, app_name: str, unit_num: int) -> str:
    """Get private address of a unit."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


async def get_app_address(ops_test: OpsTest, app_name: str) -> str:
    """Get address of an app."""
    status = await ops_test.model.get_status()  # noqa: F821
    return status["applications"][app_name]["public-address"]


@pytest.mark.skip_if_deployed
@pytest.mark.abort_on_fail
async def test_build_and_deploy(ops_test: OpsTest, local_charm: Path) -> None:
    """Build the charm-under-test and deploy it.

    Assert on the unit status before any relations/configurations take place.
    """
    await ops_test.model.deploy(
        "postgresql-k8s",
        channel="14/stable",
        trust=True,
        config={"plugin_pg_trgm_enable": "True", "plugin_btree_gin_enable": "True"},
    )
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}
    await ops_test.model.deploy(
        entity_url=str(local_charm),
        resources=resources,
        application_name=KRATOS_APP,
        trust=True,
        series="jammy",
    )
    await ops_test.model.integrate(KRATOS_APP, DB_APP)

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP, DB_APP],
        status="active",
        raise_on_blocked=False,
        raise_on_error=False,
        timeout=1000,
    )


@pytest.mark.skip_if_deployed
async def test_ingress_relation(ops_test: OpsTest) -> None:
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_PUBLIC_APP,
        trust=True,
        channel="latest/stable",
        config={"external_hostname": "some_hostname"},
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_ADMIN_APP,
        trust=True,
        channel="latest/stable",
        config={"external_hostname": "some_hostname"},
    )
    await ops_test.model.integrate(f"{KRATOS_APP}:internal-ingress", TRAEFIK_ADMIN_APP)
    await ops_test.model.integrate(f"{KRATOS_APP}:public-ingress", TRAEFIK_PUBLIC_APP)

    await ops_test.model.wait_for_idle(
        apps=[TRAEFIK_PUBLIC_APP, TRAEFIK_ADMIN_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )


async def test_has_public_ingress(ops_test: OpsTest) -> None:
    # Get the traefik address and try to reach kratos
    public_address = await get_unit_address(ops_test, TRAEFIK_PUBLIC_APP, 0)

    resp = requests.get(
        f"http://{public_address}/{ops_test.model.name}-{KRATOS_APP}/.well-known/ory/webauthn.js"
    )

    assert resp.status_code == 200


async def test_has_internal_ingress(ops_test: OpsTest) -> None:
    # Get the traefik address and try to reach kratos
    internal_address = await get_unit_address(ops_test, TRAEFIK_ADMIN_APP, 0)

    # test admin endpoint
    assert (
        requests.get(
            f"http://{internal_address}/{ops_test.model.name}-{KRATOS_APP}/admin/identities"
        ).status_code
        == 200
    )
    # test public endpoint
    assert (
        requests.get(
            f"http://{internal_address}/{ops_test.model.name}-{KRATOS_APP}/sessions/whoami"
        ).status_code
        == 401
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

    res = (await action.wait()).results

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


async def test_identity_schemas_config(ops_test: OpsTest) -> None:
    public_address = await get_unit_address(ops_test, TRAEFIK_PUBLIC_APP, 0)
    resp = requests.get(f"http://{public_address}/{ops_test.model.name}-{KRATOS_APP}/schemas")

    original_resp = resp.json()

    schema_id = "user_v1"
    await ops_test.model.applications[KRATOS_APP].set_config({
        "identity_schemas": json.dumps({schema_id: IDENTITY_SCHEMA}),
        "default_identity_schema_id": schema_id,
    })

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    for _ in range(40):
        resp = requests.get(f"http://{public_address}/{ops_test.model.name}-{KRATOS_APP}/schemas")
        # It may take some time for the changes to take effect, so we wait and retry
        if len(resp.json()) != 1:
            await sleep(3)
        else:
            break

    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == schema_id

    await ops_test.model.applications[KRATOS_APP].set_config({
        "identity_schemas": "",
        "default_identity_schema_id": "",
    })

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    for _ in range(40):
        resp = requests.get(f"http://{public_address}/{ops_test.model.name}-{KRATOS_APP}/schemas")
        # It may take some time for the changes to take effect, so we wait and retry
        if len(resp.json()) != 2:
            await sleep(3)
        else:
            break

    assert all(s in original_resp for s in resp.json())
    assert len(original_resp) == len(resp.json())


async def test_kratos_scale_up(ops_test: OpsTest) -> None:
    """Check that kratos works after it is scaled up."""
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
    """Check that kratos works after it is scaled down."""
    app = ops_test.model.applications[KRATOS_APP]

    await app.scale(1)

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        timeout=1000,
    )
