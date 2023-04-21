#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Interface library for creating network policies.
This library provides a Python API for creating kubernetes network policies.
## Getting Started
To get started using the library, you need to fetch the library using `charmcraft`.
```shell
cd some-charm
charmcraft fetch-lib charms.kratos.v0.kubernetes_network_policies
```
Then, to initialise the library:
```python
from charms.kratos.v0.kubernetes_network_policies import (
    K8sNetworkPoliciesHandler,
    NetworkPoliciesHandlerError,
    PortDefinition,
)
Class SomeCharm(CharmBase):
    def __init__(self, *args):
        self.network_policy_handler = K8sNetworkPoliciesHandler(self)

    def some_event_function():
        policies = [(PortDefinition("admin"), [self.admin_ingress_relation]), (PortDefinition(8080), [])]
        self.network_policy_handler.apply_ingress_policy(policies)
```

The function in this example will only allow traffic to the charm pod to the "admin" port from the app on the
other side of the `admin_ingress_relation` and all traffic to the "8080" port. Ingress traffic to all other ports
will be denied.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

from lightkube import ApiError, Client
from lightkube.models.meta_v1 import LabelSelector, ObjectMeta
from lightkube.models.networking_v1 import (
    NetworkPolicyEgressRule,
    NetworkPolicyIngressRule,
    NetworkPolicyPeer,
    NetworkPolicyPort,
    NetworkPolicySpec,
)
from lightkube.resources.networking_v1 import NetworkPolicy
from ops.charm import CharmBase
from ops.model import Relation


# The unique Charmhub library identifier, never change it
LIBID = "f0a1c7a9bc084be09b1052810651b7ed"

# Increment this major API version when introducing breaking changes
LIBAPI = 0

# Increment this PATCH version before using `charmcraft publish-lib` or reset
# to 0 if you are raising the major API version
LIBPATCH = 1

logger = logging.getLogger(__name__)


class NetworkPoliciesHandlerError(Exception):
    """Applying the network policies failed."""


Port = Union[str, int]
IngressPolicyDefinition = Tuple[Port, List[Relation]]


class KubernetesNetworkPoliciesHandler:
    """A helper class for managing kubernetes network policies."""

    def __init__(self, charm: CharmBase) -> None:
        self._charm = charm
        self.client = Client(field_manager=charm.app.name, namespace=charm.model.name)

    @property
    def policy_name(self) -> str:
        """The default policy name that will be created."""
        return f"{self._charm.app.name}-network-policy"

    def apply_ingress_policy(
        self, policies: IngressPolicyDefinition, name: Optional[str] = None
    ) -> None:
        """Apply an ingress network policy about a related application.

        Policies can be defined for multiple ports at once to allow ingress traffic
        from related applications

        If no policies are defined then all ingress traffic will be denied.

        Example usage:

            policies = [("admin", [admin_ingress_relation]), (8080, [public_ingress_relation])]
            network_policy_handler.apply_ingress_policy(policies)
        """
        if not name:
            name = self.policy_name

        ingress = []
        for port, relations in policies:
            selectors = [
                NetworkPolicyPeer(
                    podSelector=LabelSelector(
                        matchLabels={"app.kubernetes.io/name": relation.app.name}
                    )
                )
                for relation in relations
                if relation and relation.app
            ]
            ingress.append(
                NetworkPolicyIngressRule(
                    from_=selectors,
                    ports=[NetworkPolicyPort(port=port, protocol="TCP")],
                ),
            )

        policy = NetworkPolicy(
            metadata=ObjectMeta(name=name),
            spec=NetworkPolicySpec(
                podSelector=LabelSelector(
                    matchLabels={
                        "app.kubernetes.io/name": self._charm.app.name,
                    }
                ),
                policyTypes=["Ingress", "Egress"],
                ingress=ingress,
            ),
        )

        try:
            self.client.apply(
                policy,
                namespace=self._charm.model.name,
            )
        except ApiError as e:
            if e.status.code == 403:
                msg = f"Kubernetes resources patch failed: `juju trust` this application. {e}"
            else:
                msg = f"Kubernetes resources patch failed: {e}"
            logger.error(msg)
            raise NetworkPoliciesHandlerError()

    def delete_network_policy(self, name: Optional[str] = None) -> None:
        """Delete a network policy rule."""
        if not name:
            name = self.policy_name

        try:
            self.client.delete(name, namespace=self._charm.model.name)
        except ApiError as e:
            if e.status.code == 403:
                msg = f"Kubernetes resources patch failed: `juju trust` this application. {e}"
            else:
                msg = f"Kubernetes resources patch failed: {e}"
            logger.error(msg)
            raise NetworkPoliciesHandlerError()
