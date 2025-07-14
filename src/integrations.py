# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any, KeysView, Optional, Type, TypeAlias, Union
from urllib.parse import urlparse

from charms.traefik_k8s.v0.traefik_route import TraefikRouteRequirer
from jinja2 import Template
from yarl import URL

from constants import KRATOS_PUBLIC_PORT as PUBLIC_PORT

logger = logging.getLogger(__name__)

JsonSerializable: TypeAlias = Union[dict[str, Any], list[Any], int, str, float, bool, Type[None]]


@dataclass(frozen=True, slots=True)
class PublicRouteData:
    """The data source from the public-route integration."""

    url: URL = URL()
    config: dict = field(default_factory=dict)

    @classmethod
    def load(cls, requirer: TraefikRouteRequirer) -> "PublicRouteData":
        model, app = requirer._charm.model.name, requirer._charm.app.name
        external_host = requirer.external_host
        external_endpoint = f"{requirer.scheme}://{external_host}"

        # template could have use PathPrefixRegexp but going for a simple one right now
        with open("templates/route.json.j2", "r") as file:
            template = Template(file.read())

        ingress_config = json.loads(
            template.render(
                model=model,
                app=app,
                public_port=PUBLIC_PORT,
                external_host=external_host,
            )
        )

        if not external_host:
            logger.error("External hostname is not set on the ingress provider")
            return cls()

        return cls(
            url=URL(external_endpoint),
            config=ingress_config,
        )

    @property
    def secured(self) -> bool:
        return self.url.scheme == "https"
