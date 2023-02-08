#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for sharing hydra endpoints.

This library provides a Python API for both requesting and providing public and admin endpoints.

## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.hydra.v0.hydra_endpoints_info
```

To use the library from the provider side (Hydra):
In the `metadata.yaml` of the charm, add the following:
```yaml
provides:
  endpoint-info:
    interface: hydra-endpoints-info
    description: Provides API endpoints to a related application
```

To use the library from the requirer side (Kratos):
In the `metadata.yaml` of the charm, add the following:
```yaml
requires:
  endpoint-info:
    interface: hydra-endpoints-info
    limit: 1
```
Then, to initialise the library:
```python
from charms.hydra.v0.hydra_endpoints_info import (
    HydraEndpointsRelationError,
    HydraEndpointsRequirer,
)

Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.hydra_endpoints_relation = HydraEndpointsRequirer(self)
        self.framework.observe(self.on.some_event_emitted, self.some_event_function)
    def some_event_function():
        # fetch the relation info
        try:
            hydra_data = self.hydra_endpoints_relation.get_relation_data()
        except HydraEndpointsRelationError as error:
            ...
```

"""

import logging

from ops.framework import Object
from ops.model import Application

# TODO: Update once the lib is published
# # The unique Charmhub library identifier, never change it
# LIBID = ""
#
# # Increment this major API version when introducing breaking changes
# LIBAPI = 0
#
# # Increment this PATCH version before using `charmcraft publish-lib` or reset
# # to 0 if you are raising the major API version
# LIBPATCH = 0

RELATION_NAME = "endpoint-info"
INTERFACE_NAME = "hydra-endpoints-info"
logger = logging.getLogger(__name__)


class HydraEndpointsRelationError(Exception):
    pass


class HydraEndpointsRelationMissingError(HydraEndpointsRelationError):
    def __init__(self):
        self.message = "Missing endpoint-info relation with hydra"
        super().__init__(self.message)


class HydraEndpointsRelationDataMissingError(HydraEndpointsRelationError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class HydraEndpointsRequirer(Object):
    def __init__(self, charm, relation_name: str = RELATION_NAME):
        super().__init__(charm, relation_name)
        self.charm = charm
        self.relation_name = relation_name

    def get_relation_data(self):
        if not self.model.unit.is_leader():
            return
        endpoints = self.model.relations[self.relation_name]
        if len(endpoints) == 0:
            raise HydraEndpointsRelationMissingError()

        remote_app = [
            app
            for app in endpoints[0].data.keys()
            if isinstance(app, Application) and not app._is_our_app
        ][0]

        data = endpoints[0].data[remote_app]

        if not "admin_endpoint" in data:
            logger.error("Missing admin endpoint in endpoint-info relation data")
            raise HydraEndpointsRelationDataMissingError(
                "Missing admin endpoint in endpoint-info relation data"
            )

        return {
            "admin_endpoint": data["admin_endpoint"],
            "public_endpoint": data["public_endpoint"],
        }
