# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

import os

import pytest
from lightkube import Client, KubeConfig

KUBECONFIG = os.environ.get("TESTING_KUBECONFIG", "~/.kube/config")


@pytest.fixture(scope="module")
def client() -> Client:
    return Client(config=KubeConfig.from_file(KUBECONFIG))
