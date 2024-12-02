# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import asyncio
import functools
from pathlib import Path
from typing import AsyncGenerator, Awaitable, Callable, Optional, Tuple

import pytest_asyncio
import yaml
from httpx import AsyncClient, Response
from pytest_operator.plugin import OpsTest

from constants import PUBLIC_INGRESS_INTEGRATION_NAME

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
KRATOS_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
CA_APP = "self-signed-certificates"
KRATOS_APP = METADATA["name"]
DB_APP = "postgresql-k8s"
PUBLIC_INGRESS_APP = "public-ingress"
ISTIO_CONTROL_PLANE_CHARM = "istio-k8s"
ISTIO_INGRESS_CHARM = "istio-ingress-k8s"
ADMIN_MAIL = "admin1@adminmail.com"
PUBLIC_INGRESS_DOMAIN = "public"
PUBLIC_LOAD_BALANCER = f"{PUBLIC_INGRESS_APP}-istio"
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


@pytest_asyncio.fixture
async def password_secret(ops_test: OpsTest) -> Tuple[str, str]:
    password = "secret"
    secrets = await ops_test.model.list_secrets({"label": "password"})
    if not secrets:
        secret_id = await ops_test.model.add_secret("password", [f"password={password}"])
        return secret_id, password

    secret_id = secrets[0].uri
    await ops_test.model.grant_secret("password", KRATOS_APP)

    return secret_id, password


@pytest_asyncio.fixture
async def http_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(verify=False) as client:
        yield client


@pytest_asyncio.fixture
async def get_schemas(
    ops_test: OpsTest,
    public_ingress_address: str,
    http_client: AsyncClient,
) -> Callable[[], Awaitable[Response]]:
    url = f"https://{public_ingress_address}/{ops_test.model_name}-{KRATOS_APP}/schemas"

    async def wrapper() -> Response:
        return await http_client.get(
            url,
            headers={"Host": PUBLIC_INGRESS_DOMAIN},
            extensions={"sni_hostname": PUBLIC_INGRESS_DOMAIN},
        )

    return wrapper


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
async def leader_public_ingress_integration_data(app_integration_data: Callable) -> Optional[dict]:
    return await app_integration_data(KRATOS_APP, PUBLIC_INGRESS_INTEGRATION_NAME)


async def get_k8s_service_address(namespace: str, service_name: str) -> str:
    cmd = [
        "kubectl",
        "-n",
        namespace,
        "get",
        f"service/{service_name}",
        "-o=jsonpath={.status.loadBalancer.ingress[0].ip}",
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await process.communicate()

    return stdout.decode().strip() if not process.returncode else ""


@pytest_asyncio.fixture
async def public_ingress_address(ops_test: OpsTest) -> str:
    return await get_k8s_service_address(ops_test.model_name, PUBLIC_LOAD_BALANCER)
