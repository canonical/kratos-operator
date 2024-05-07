#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Library for sharing Istio Gateway(s) information.

This library offers a Python API for providing and requesting information about
Istio Gateway(s) by wrapping the `gateway-info` relation endpoints.
The default relation name is `gateway-info` and it's recommended to use that name,
though if changed, you must ensure to pass the correct name when instantiating the
provider and requirer classes, as well as in `metadata.yaml`.

## Getting Started

### Fetching the library with charmcraft

Using charmcraft you can:
```shell
charmcraft fetch-lib charms.istio_pilot.v0.istio_gateway_info
```

## Using the library as requirer

### Add relation to metadata.yaml
```yaml
requires:
  gateway-info:
    interface: istio-gateway-info
    limit: 1
```

### Instantiate the GatewayRequirer class in charm.py

```python
from ops.charm import CharmBase
from charms.istio_pilot.v0.istio_gateway_info import GatewayRequirer, GatewayRelationError

class RequirerCharm(CharmBase):
    def __init__(self, *args):
        self.gateway = GatewayRequirer(self)
        self.framework.observe(self.on.some_event_emitted, self.some_event_function)

    def some_event_function():
        # use the getter function wherever the info is needed
        try:
            gateway_data = self.gateway_relation.get_relation_data()
        except GatewayRelationError as error:
            "your error handler goes here"
```

## Using the library as provider

### Add relation to metadata.yaml
```yaml
provides:
  gateway-info:
    interface: istio-gateway-info
```

### Instantiate the GatewayProvider class in charm.py

```python
from ops.charm import CharmBase
from charms.istio_pilot.v0.istio_gateway_info import GatewayProvider, GatewayRelationError

class ProviderCharm(CharmBase):
    def __init__(self, *args, **kwargs):
        ...
        self.gateway_provider = GatewayProvider(self)
        self.observe(self.on.some_event, self._some_event_handler)
    def _some_event_handler(self, ...):
        # This will update the relation data bag with the Gateway name and namespace
        try:
            self.gateway_provider.send_gateway_data(charm, gateway_name, gateway_namespace)
        except GatewayRelationError as error:
            "your error handler goes here"
```

Note that GatewayProvider.send_gateway_data() sends data to all related applications, and will
execute without error even if no applications are related. If you want to ensure that the someone
is listening for the data, please add checks separately.

## Relation data

The data shared by this library is:
* gateway_name: the name of the Gateway the provider knows about. It corresponds to
  the `name` field in the Gateway definition
* gateway_namespace: the namespace where the Gateway is deployed.
* gateway_up: (new in v0.3) boolean indicating whether the Gateway is up.  This being True
  indicates that the Gateway should be fully established and accepting traffic.
  If relating a Requirer of v0.3 to a Provider using v0.2 or earlier of this library, the Requirer
  will return gateway_up=True by default.

The following example shows an Istio Gateway with `gateway_name=my-gateway` and
`gateway_namespace=my-gateway-namespace`

```yaml
apiVersion: networking.istio.io/v1alpha3
kind: Gateway
metadata:
  name: my-gateway
  namespace: my-gateway-namespace
```

"""

import logging

from ops.framework import Object
from ops.model import Relation

# The unique Charmhub library identifier, never change it
LIBID = "354103422e7a43e2870e4203fbb5a649"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 4

# Default relation and interface names. If changed, consistency must be kept
# across the provider and requirer.
DEFAULT_RELATION_NAME = "gateway-info"
DEFAULT_INTERFACE_NAME = "istio-gateway-info"
REQUIRED_ATTRIBUTES = ["gateway_name", "gateway_namespace"]

logger = logging.getLogger(__name__)


class GatewayRelationError(Exception):
    pass


class GatewayRelationMissingError(GatewayRelationError):
    def __init__(self):
        self.message = "Missing gateway-info relation."
        super().__init__(self.message)


class GatewayRelationDataMissingError(GatewayRelationError):
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)


class GatewayRequirer(Object):
    """Base class that represents a requirer relation end.

    Args:
        requirer_charm (CharmBase): the requirer application
        relation_name (str, optional): the name of the relation

    Attributes:
        requirer_charm (CharmBase): variable for storing the requirer application
        relation_name (str): variable for storing the name of the relation
    """

    def __init__(self, requirer_charm, relation_name: str = DEFAULT_RELATION_NAME):
        super().__init__(requirer_charm, relation_name)
        # TODO: remove this attribute, we are not really using it at all.
        # Leaving it to keep backwards compatibility.
        self.requirer_charm = requirer_charm
        self.relation_name = relation_name

    @staticmethod
    def _relation_preflight_checks(relation: Relation) -> None:
        """Series of checks for the relation and relation data.
        Args:
            relation (Relation): the relation object to run the checks on
        Raises:
            GatewayRelationDataMissingError: if data is missing or incomplete
            GatewayRelationMissingError: if there is no related application
            ops.model.TooManyRelatedAppsError: if there is more than one related application
        """
        # Raise if there is no related application
        if not relation:
            raise GatewayRelationMissingError()

        # Extract remote app information from relation
        remote_app = relation.app
        # Get relation data from remote app
        relation_data = relation.data[remote_app]

        # Raise if there is no data found in the relation data bag
        if not relation_data:
            raise GatewayRelationDataMissingError("No data found in relation data bag.")

        # Check if the relation data contains the expected attributes
        missing_attributes = [
            attribute for attribute in REQUIRED_ATTRIBUTES if attribute not in relation_data
        ]
        if missing_attributes:
            raise GatewayRelationDataMissingError(f"Missing attributes: {missing_attributes}")

    def get_relation_data(self) -> dict:
        """Returns a dictionary with the Gateway information.

        Raises:
            GatewayRelationDataMissingError: if data is missing entirely or some attributes
            GatewayRelationMissingError: if there is no related application
        """
        # Run pre-flight checks
        # Raises TooManyRelatedAppsError if related to more than one app
        relation = self.model.get_relation(self.relation_name)
        self._relation_preflight_checks(relation=relation)

        # Get relation data from remote app
        relation_data = relation.data[relation.app]

        # Convert string gateway_up back to boolean, defaulting to True if it does not exist.
        gateway_up = relation_data.get("gateway_up", "true")
        gateway_up = gateway_up.lower() == "true"
        gateway_ip = relation_data.get("gateway_ip")
        gateway_dns = relation_data.get("gateway_dns")

        return {
            "gateway_name": relation_data["gateway_name"],
            "gateway_namespace": relation_data["gateway_namespace"],
            "gateway_up": gateway_up,
            "gateway_ip": gateway_ip,
            "gateway_dns": gateway_dns,
        }


class GatewayProvider(Object):
    """Base class that represents a provider relation end.

    Args:
        provider_charm (CharmBase): the provider application
        relation_name (str, optional): the name of the relation

    Attributes:
        provider_charm (CharmBase): variable for storing the provider application
        relation_name (str): variable for storing the name of the relation
    """

    def __init__(self, provider_charm, relation_name: str = DEFAULT_RELATION_NAME):
        super().__init__(provider_charm, relation_name)
        self.provider_charm = provider_charm
        self.relation_name = relation_name

    def send_gateway_relation_data(
        self,
        gateway_name: str,
        gateway_namespace: str,
        gateway_ip: str,
        gateway_up: bool = True,
        gateway_dns: str = "",
    ) -> None:
        """Updates the relation data bag with data from the local gateway.

        This method will complete successfully even if there are no related applications.

        Args:
            gateway_name (str): the name of the Gateway the provider knows about
            gateway_namespace(str): the namespace of the Gateway the provider knows about
            gateway_up (bool): (optional) the status of the Gateway.  Defaults to True if not
                               provided.
        """
        # Update the relation data bag with localgateway information
        relations = self.model.relations[self.relation_name]

        # Update relation data
        for relation in relations:
            relation.data[self.provider_charm.app].update(
                {
                    "gateway_name": gateway_name,
                    "gateway_namespace": gateway_namespace,
                    "gateway_up": str(gateway_up).lower(),
                    "gateway_ip": gateway_ip,
                    "gateway_dns": gateway_dns,
                }
            )
