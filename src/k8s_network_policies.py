#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

"""A helper class for managing kubernetes network policies."""

import logging
from typing import List, Optional, Tuple, Union

from lightkube import ApiError, Client
from lightkube.models.meta_v1 import LabelSelector, ObjectMeta
from lightkube.models.networking_v1 import (
    NetworkPolicyIngressRule,
    NetworkPolicyPeer,
    NetworkPolicyPort,
    NetworkPolicySpec,
)
from lightkube.resources.networking_v1 import NetworkPolicy
from ops.charm import CharmBase
from ops.model import Relation

logger = logging.getLogger(__name__)


class NetworkPoliciesHandlerError(Exception):
    """Applying the network policies failed."""


IngressPolicyDefinition = Tuple[Union[str, int], List[Relation]]


class K8sNetworkPoliciesHandler:
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
                    ports=[NetworkPolicyPort(port=port)],
                ),
            )

        policy = NetworkPolicy(
            metadata=ObjectMeta(name=name),
            spec=NetworkPolicySpec(
                podSelector=LabelSelector(
                    matchLabels={"app.kubernetes.io/name": self._charm.app.name}
                ),
                policyTypes=["Ingress"],
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
