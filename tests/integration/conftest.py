# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import os
from typing import Tuple

import pytest
import pytest_asyncio
import yaml
from lightkube import Client, KubeConfig
from pytest_operator.plugin import OpsTest

from tests.integration.test_charm import KRATOS_APP

KUBECONFIG = os.environ.get("TESTING_KUBECONFIG", "~/.kube/config")


@pytest.fixture(scope="module")
def client() -> Client:
    return Client(config=KubeConfig.from_file(KUBECONFIG))


@pytest_asyncio.fixture
async def get_secret(ops_test: OpsTest, secret_id: str) -> dict:
    show_secret_cmd = f"show-secret {secret_id} --reveal".split()
    _, stdout, _ = await ops_test.juju(*show_secret_cmd)
    cmd_output = yaml.safe_load(stdout)
    return cmd_output[secret_id]


@pytest_asyncio.fixture
async def password_secret(ops_test: OpsTest) -> Tuple[str, str]:
    password = "secret"
    secrets = await ops_test.model.list_secrets({"label": "password"})
    if not secrets:
        secret_id = await ops_test.model.add_secret("password", [f"password={password}"])
    else:
        secret_id = secrets[0].uri
    await ops_test.model.grant_secret("password", KRATOS_APP)

    return secret_id, password
