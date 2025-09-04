# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import functools
import os
import re
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable, Optional

import httpx
import pytest
import pytest_asyncio
import yaml
from httpx import AsyncClient, Response
from juju.application import Application
from juju.unit import Unit
from pytest_operator.plugin import OpsTest

from constants import (
    INTERNAL_INGRESS_INTEGRATION_NAME,
    KRATOS_INFO_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_INGRESS_INTEGRATION_NAME,
)

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
KRATOS_APP = METADATA["name"]
KRATOS_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
TRAEFIK_CHARM = "traefik-k8s"
DB_APP = "postgresql-k8s"
LOGIN_UI_APP = "identity-platform-login-ui-operator"
TRAEFIK_PUBLIC_APP = "traefik-public"
TRAEFIK_ADMIN_APP = "traefik-admin"
PUBLIC_INGRESS_DOMAIN = "public"
ADMIN_INGRESS_DOMAIN = "admin"
ADMIN_EMAIL = "admin1@adminmail.com"
ADMIN_PASSWORD = "admin"
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


async def integrate_dependencies(ops_test: OpsTest) -> None:
    await ops_test.model.integrate(KRATOS_APP, DB_APP)
    await ops_test.model.integrate(
        f"{KRATOS_APP}:{LOGIN_UI_INTEGRATION_NAME}", f"{LOGIN_UI_APP}:{LOGIN_UI_INTEGRATION_NAME}"
    )
    await ops_test.model.integrate(
        f"{KRATOS_APP}:{INTERNAL_INGRESS_INTEGRATION_NAME}", TRAEFIK_ADMIN_APP
    )
    await ops_test.model.integrate(
        f"{KRATOS_APP}:{PUBLIC_INGRESS_INTEGRATION_NAME}", TRAEFIK_PUBLIC_APP
    )
    await ops_test.model.integrate(
        f"{KRATOS_APP}:{KRATOS_INFO_INTEGRATION_NAME}",
        f"{LOGIN_UI_APP}:{KRATOS_INFO_INTEGRATION_NAME}",
    )


async def get_unit_data(ops_test: OpsTest, unit_name: str) -> dict:
    show_unit_cmd = (f"show-unit {unit_name}").split()
    _, stdout, _ = await ops_test.juju(*show_unit_cmd)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[unit_name]


async def get_integration_data(
    ops_test: OpsTest, app_name: str, integration_name: str, unit_num: int = 0
) -> Optional[dict]:
    data = await get_unit_data(ops_test, f"{app_name}/{unit_num}")
    return next(
        (
            integration
            for integration in data["relation-info"]
            if integration["endpoint"] == integration_name
        ),
        None,
    )


async def get_app_integration_data(
    ops_test: OpsTest,
    app_name: str,
    integration_name: str,
    unit_num: int = 0,
) -> Optional[dict]:
    data = await get_integration_data(ops_test, app_name, integration_name, unit_num)
    return data["application-data"] if data else None


@pytest_asyncio.fixture
async def app_integration_data(ops_test: OpsTest) -> Callable:
    return functools.partial(get_app_integration_data, ops_test)


@pytest_asyncio.fixture
async def leader_peer_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(KRATOS_APP, PEER_INTEGRATION_NAME)


@pytest_asyncio.fixture
async def leader_login_ui_endpoint_integration_data(
    app_integration_data: Callable,
) -> Optional[dict]:
    return await app_integration_data(KRATOS_APP, LOGIN_UI_INTEGRATION_NAME)


@pytest_asyncio.fixture
async def leader_public_ingress_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(KRATOS_APP, PUBLIC_INGRESS_INTEGRATION_NAME)


@pytest_asyncio.fixture
async def leader_internal_ingress_integration_data(
    app_integration_data: Callable,
) -> Optional[dict]:
    return await app_integration_data(KRATOS_APP, INTERNAL_INGRESS_INTEGRATION_NAME)


@pytest_asyncio.fixture
async def leader_kratos_info_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(LOGIN_UI_APP, KRATOS_INFO_INTEGRATION_NAME)


async def unit_address(ops_test: OpsTest, *, app_name: str, unit_num: int = 0) -> str:
    status = await ops_test.model.get_status()
    return status["applications"][app_name]["units"][f"{app_name}/{unit_num}"]["address"]


@pytest_asyncio.fixture
async def public_address() -> Callable[[OpsTest, int], Awaitable[str]]:
    return functools.partial(unit_address, app_name=TRAEFIK_PUBLIC_APP)


@pytest_asyncio.fixture
async def admin_address() -> Callable[[OpsTest, int], Awaitable[str]]:
    return functools.partial(unit_address, app_name=TRAEFIK_ADMIN_APP)


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(verify=False) as client:
        yield client


@pytest_asyncio.fixture
async def get_webauthn_js(
    ops_test: OpsTest,
    public_address: Callable,
    admin_address: Callable,
    http_client: AsyncClient,
) -> Response:
    address = await public_address(ops_test)
    url = f"http://{address}/{ops_test.model_name}-{KRATOS_APP}/.well-known/ory/webauthn.js"
    return await http_client.get(url)


@pytest_asyncio.fixture
async def get_identity_schemas(
    ops_test: OpsTest,
    public_address: Callable,
    http_client: AsyncClient,
) -> Callable[[], Awaitable[Response]]:
    address = await public_address(ops_test)

    async def wrapper() -> Response:
        url = f"http://{address}/{ops_test.model_name}-{KRATOS_APP}/schemas"
        return await http_client.get(url)

    return wrapper


@pytest_asyncio.fixture
async def get_identities(
    ops_test: OpsTest, admin_address: Callable, http_client: AsyncClient
) -> Response:
    address = await admin_address(ops_test)
    url = f"http://{address}/{ops_test.model_name}-{KRATOS_APP}/admin/identities"
    return await http_client.get(url)


@pytest_asyncio.fixture
async def get_whoami(
    ops_test: OpsTest, admin_address: Callable, http_client: AsyncClient
) -> Response:
    address = await admin_address(ops_test)
    url = f"http://{address}/{ops_test.model_name}-{KRATOS_APP}/sessions/whoami"
    return await http_client.get(url)


@pytest_asyncio.fixture
async def password_secret(ops_test: OpsTest) -> Callable[[str, str], Awaitable[str]]:
    async def _create_secret(label: str, password: str) -> str:
        secrets = await ops_test.model.list_secrets({"label": label})
        if not secrets:
            secret_id = await ops_test.model.add_secret(label, [f"password={password}"])
        else:
            secret_id = secrets[0].uri

        await ops_test.model.grant_secret(label, KRATOS_APP)
        return secret_id

    return _create_secret


@pytest_asyncio.fixture
async def admin_password_secret(password_secret: Callable) -> str:
    return await password_secret("admin-password", ADMIN_PASSWORD)


@pytest_asyncio.fixture
async def new_admin_password_secret(password_secret: Callable) -> str:
    return await password_secret("new-admin-password", f"new-{ADMIN_PASSWORD}")


@pytest_asyncio.fixture(scope="module")
async def local_charm(ops_test: OpsTest) -> str | Path:
    # in GitHub CI, charms are built with charmcraftcache and uploaded to $CHARM_PATH
    charm = os.getenv("CHARM_PATH")
    if not charm:
        # fall back to build locally - required when run outside of GitHub CI
        charm = await ops_test.build_charm(".")
    return charm


@pytest.fixture(scope="session")
def kratos_version() -> str:
    matched = re.search(r"(?P<version>\d+\.\d+\.\d+)", KRATOS_IMAGE)
    return f"v{matched.group('version')}" if matched else ""


@pytest.fixture
def migration_key(ops_test: OpsTest) -> str:
    db_integration = next(
        (
            integration
            for integration in ops_test.model.relations
            if integration.matches(f"{KRATOS_APP}:pg-database", f"{DB_APP}:database")
        ),
        None,
    )
    return f"migration_version_{db_integration.entity_id}" if db_integration else ""


@pytest.fixture
def kratos_application(ops_test: OpsTest) -> Application:
    return ops_test.model.applications[KRATOS_APP]


@pytest.fixture
def kratos_unit(kratos_application: Application) -> Unit:
    return kratos_application.units[0]
