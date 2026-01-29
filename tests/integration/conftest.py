# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

import logging
import os
import re
import secrets
import subprocess
from contextlib import suppress
from pathlib import Path
from typing import Callable, Generator

import jubilant
import pytest
import requests
from integration.constants import (
    ADMIN_PASSWORD,
    DB_APP,
    KRATOS_APP,
    KRATOS_IMAGE,
    LOGIN_UI_APP,
    TRAEFIK_ADMIN_APP,
    TRAEFIK_PUBLIC_APP,
)
from integration.utils import (
    get_app_integration_data,
    get_integration_data,
    get_unit_address,
    juju_model_factory,
)

from src.constants import (
    INTERNAL_ROUTE_INTEGRATION_NAME,
    KRATOS_INFO_INTEGRATION_NAME,
    LOGIN_UI_INTEGRATION_NAME,
    PEER_INTEGRATION_NAME,
    PUBLIC_ROUTE_INTEGRATION_NAME,
)

logger = logging.getLogger(__name__)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add custom command-line options for model management and deployment control."""
    parser.addoption(
        "--keep-models",
        "--no-teardown",
        action="store_true",
        dest="no_teardown",
        default=False,
        help="Keep the model after the test is finished.",
    )
    parser.addoption(
        "--model",
        action="store",
        dest="model",
        default=None,
        help="The model to run the tests on.",
    )
    parser.addoption(
        "--no-deploy",
        "--no-setup",
        action="store_true",
        dest="no_setup",
        default=False,
        help="Skip deployment of the charm.",
    )


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line("markers", "setup: tests that setup some parts of the environment")
    config.addinivalue_line(
        "markers", "teardown: tests that teardown some parts of the environment."
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Modify collected test items based on command-line options."""
    skip_setup = pytest.mark.skip(reason="no_setup provided")
    skip_teardown = pytest.mark.skip(reason="no_teardown provided")
    for item in items:
        if config.getoption("no_setup") and "setup" in item.keywords:
            item.add_marker(skip_setup)
        if config.getoption("no_teardown") and "teardown" in item.keywords:
            item.add_marker(skip_teardown)


@pytest.fixture(scope="module")
def juju(request: pytest.FixtureRequest) -> Generator[jubilant.Juju, None, None]:
    """Create a temporary Juju model for integration tests."""
    model_name = request.config.getoption("--model")
    if not model_name:
        model_name = f"test-kratos-{secrets.token_hex(4)}"

    juju_ = juju_model_factory(model_name)
    juju_.wait_timeout = 10 * 60

    try:
        yield juju_
    finally:
        if request.session.testsfailed:
            log = juju_.debug_log(limit=1000)
            print(log, end="")

        no_teardown = bool(request.config.getoption("--no-teardown"))
        keep_model = no_teardown or request.session.testsfailed > 0
        if not keep_model:
            with suppress(jubilant.CLIError):
                args = [
                    "destroy-model",
                    juju_.model,
                    "--no-prompt",
                    "--destroy-storage",
                    "--force",
                    "--timeout",
                    "600s",
                ]
                juju_.cli(*args, include_model=False)


@pytest.fixture(scope="session")
def local_charm() -> Path:
    """Get the path to the charm-under-test."""
    charm: str | Path | None = os.getenv("CHARM_PATH")
    if not charm:
        subprocess.run(["charmcraft", "pack"], check=True)
        if not (charms := list(Path(".").glob("*.charm"))):
            raise RuntimeError("Charm not found and build failed")
        charm = charms[0].absolute()
    return Path(charm)


@pytest.fixture
def http_client() -> Generator[requests.Session, None, None]:
    with requests.Session() as client:
        client.verify = False
        yield client


def integrate_dependencies(juju: jubilant.Juju) -> None:
    juju.integrate(KRATOS_APP, DB_APP)
    juju.integrate(
        f"{KRATOS_APP}:{LOGIN_UI_INTEGRATION_NAME}", f"{LOGIN_UI_APP}:{LOGIN_UI_INTEGRATION_NAME}"
    )
    juju.integrate(f"{KRATOS_APP}:{INTERNAL_ROUTE_INTEGRATION_NAME}", TRAEFIK_ADMIN_APP)
    juju.integrate(f"{KRATOS_APP}:{PUBLIC_ROUTE_INTEGRATION_NAME}", TRAEFIK_PUBLIC_APP)
    juju.integrate(
        f"{KRATOS_APP}:{KRATOS_INFO_INTEGRATION_NAME}",
        f"{LOGIN_UI_APP}:{KRATOS_INFO_INTEGRATION_NAME}",
    )


@pytest.fixture
def app_integration_data(juju: jubilant.Juju) -> Callable:
    def _get_data(app_name: str, integration_name: str, unit_num: int = 0) -> dict | None:
        return get_app_integration_data(juju, app_name, integration_name, unit_num)

    return _get_data


@pytest.fixture
def leader_peer_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(KRATOS_APP, PEER_INTEGRATION_NAME)


@pytest.fixture
def leader_login_ui_endpoint_integration_data(
    app_integration_data: Callable,
) -> dict | None:
    return app_integration_data(KRATOS_APP, LOGIN_UI_INTEGRATION_NAME)


@pytest.fixture
def leader_public_route_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(KRATOS_APP, PUBLIC_ROUTE_INTEGRATION_NAME)


@pytest.fixture
def leader_internal_ingress_integration_data(
    app_integration_data: Callable,
) -> dict | None:
    return app_integration_data(KRATOS_APP, INTERNAL_ROUTE_INTEGRATION_NAME)


@pytest.fixture
def leader_kratos_info_integration_data(app_integration_data: Callable) -> dict | None:
    return app_integration_data(LOGIN_UI_APP, KRATOS_INFO_INTEGRATION_NAME)


@pytest.fixture
def public_address(juju: jubilant.Juju) -> str:
    return get_unit_address(juju, app_name=TRAEFIK_PUBLIC_APP)


@pytest.fixture
def admin_address(juju: jubilant.Juju) -> str:
    return get_unit_address(juju, app_name=TRAEFIK_ADMIN_APP)


@pytest.fixture
def get_webauthn_js(
    public_address: str,
    http_client: requests.Session,
) -> requests.Response:
    url = f"https://{public_address}/.well-known/webauthn.js"
    return http_client.get(url)


@pytest.fixture
def get_identity_schemas(
    public_address: str,
    http_client: requests.Session,
) -> Callable[[], requests.Response]:

    def wrapper() -> requests.Response:
        url = f"https://{public_address}/schemas"
        return http_client.get(url)

    return wrapper


@pytest.fixture
def get_identities(admin_address: str, http_client: requests.Session) -> requests.Response:
    url = f"http://{admin_address}/admin/identities"
    return http_client.get(url)


@pytest.fixture
def get_whoami(admin_address: str, http_client: requests.Session) -> requests.Response:
    url = f"http://{admin_address}/sessions/whoami"
    return http_client.get(url)


@pytest.fixture
def password_secret(juju: jubilant.Juju) -> Callable[[str, str], str]:
    def _create_secret(label: str, password: str) -> str:
        try:
            secret = juju.show_secret(label)
            sid = secret.uri.unique_identifier
        except jubilant.CLIError:
            secret_uri = juju.add_secret(label, {"password": password})
            sid = secret_uri.unique_identifier

        juju.grant_secret(sid, KRATOS_APP)
        return sid

    return _create_secret


@pytest.fixture
def admin_password_secret(password_secret: Callable) -> str:
    return password_secret("admin-password", ADMIN_PASSWORD)


@pytest.fixture
def new_admin_password_secret(password_secret: Callable) -> str:
    return password_secret("new-admin-password", f"new-{ADMIN_PASSWORD}")


@pytest.fixture(scope="session")
def kratos_version() -> str:
    matched = re.search(r"(?P<version>\d+\.\d+\.\d+)", KRATOS_IMAGE)
    return f"v{matched.group('version')}" if matched else ""


@pytest.fixture
def migration_key(juju: jubilant.Juju) -> str:
    data = get_integration_data(juju, KRATOS_APP, "pg-database")
    return f"migration_version_{data['relation-id']}" if data else ""
