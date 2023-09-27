#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from pathlib import Path

import pytest
import requests
import yaml
from pytest_operator.plugin import OpsTest

logger = logging.getLogger(__name__)

METADATA = yaml.safe_load(Path("./metadata.yaml").read_text())
KRATOS_APP = METADATA["name"]
DB_APP = "postgresql-k8s"
TRAEFIK_CHARM = "traefik-k8s"
TRAEFIK_ADMIN_APP = "traefik-admin"
TRAEFIK_PUBLIC_APP = "traefik-public"
ADMIN_MAIL = "admin@adminmail.com"
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
async def test_build_and_deploy(ops_test: OpsTest) -> None:
    """Build the charm-under-test and deploy it.

    Assert on the unit status before any relations/configurations take place.
    """
    await ops_test.model.deploy(
        "postgresql-k8s",
        channel="14/stable",
        trust=True,
    )
    charm = await ops_test.build_charm(".")
    resources = {"oci-image": METADATA["resources"]["oci-image"]["upstream-source"]}
    await ops_test.model.deploy(
        charm,
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
        timeout=1000,
    )


async def test_ingress_relation(ops_test: OpsTest) -> None:
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_PUBLIC_APP,
        channel="latest/edge",
        config={"external_hostname": "some_hostname"},
    )
    await ops_test.model.deploy(
        TRAEFIK_CHARM,
        application_name=TRAEFIK_ADMIN_APP,
        channel="latest/edge",
        config={"external_hostname": "some_hostname"},
    )
    await ops_test.model.integrate(f"{KRATOS_APP}:admin-ingress", TRAEFIK_ADMIN_APP)
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


async def test_has_admin_ingress(ops_test: OpsTest) -> None:
    # Get the traefik address and try to reach kratos
    admin_address = await get_unit_address(ops_test, TRAEFIK_ADMIN_APP, 0)

    resp = requests.get(
        f"http://{admin_address}/{ops_test.model.name}-{KRATOS_APP}/admin/identities"
    )

    assert resp.status_code == 200


@pytest.mark.abort_on_fail
async def test_create_admin_account(ops_test: OpsTest) -> None:
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
                "password": "123456",
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


@pytest.mark.skip(
    reason=("the recovery and settings UI page must be provided to kratos for this test to work")
)
async def test_reset_password(ops_test: OpsTest) -> None:
    action = (
        await ops_test.model.applications[KRATOS_APP]
        .units[0]
        .run_action(
            "reset-password",
            email=ADMIN_MAIL,
        )
    )

    res = (await action.wait()).results

    assert "recovery_link" in res


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
    await ops_test.model.applications[KRATOS_APP].set_config(
        dict(
            identity_schemas=json.dumps({schema_id: IDENTITY_SCHEMA}),
            default_identity_schema_id=schema_id,
        )
    )

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    resp = requests.get(f"http://{public_address}/{ops_test.model.name}-{KRATOS_APP}/schemas")

    assert len(resp.json()) == 1
    assert resp.json()[0]["id"] == schema_id

    await ops_test.model.applications[KRATOS_APP].set_config(
        dict(
            identity_schemas="",
            default_identity_schema_id="",
        )
    )

    await ops_test.model.wait_for_idle(
        apps=[KRATOS_APP],
        status="active",
        raise_on_blocked=True,
        timeout=1000,
    )

    resp = requests.get(f"http://{public_address}/{ops_test.model.name}-{KRATOS_APP}/schemas")

    assert original_resp == resp.json()


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
