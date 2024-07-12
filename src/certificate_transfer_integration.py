# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper class for trusting ca chains."""

import subprocess
from pathlib import Path
from typing import Callable, Union

from charms.certificate_transfer_interface.v0.certificate_transfer import (
    CertificateAvailableEvent,
    CertificateRemovedEvent,
    CertificateTransferRequires,
)
from ops import CharmBase, Object

from constants import CERTIFICATE_TRANSFER_NAME

LOCAL_CA_CERTS_PATH = Path("/usr/local/share/ca-certificates")
BUNDLE_PATH = "/etc/ssl/certs/ca-certificates.crt"


class CertTransfer(Object):
    def __init__(
        self,
        charm: CharmBase,
        container_name: str,
        callback_fn: Callable,
        cert_transfer_relation_name: str = CERTIFICATE_TRANSFER_NAME,
        bundle_name: str = "ca-certificates.crt",
    ):
        super().__init__(charm, cert_transfer_relation_name)
        self.charm = charm
        self.container = charm.unit.get_container(container_name)
        self.cert_transfer = CertificateTransferRequires(charm, cert_transfer_relation_name)
        self.callback_fn = callback_fn
        self.bundle_name = bundle_name

        self.framework.observe(
            self.cert_transfer.on.certificate_available, self._on_certificate_event
        )
        self.framework.observe(
            self.cert_transfer.on.certificate_removed, self._on_certificate_event
        )

    @property
    def ca_bundle(self) -> str:
        bundle = set()
        for relation in self.charm.model.relations.get(self.cert_transfer.relationship_name, []):
            for unit in set(relation.units).difference([self.charm.app, self.charm.unit]):
                if ca := relation.data[unit].get("ca"):
                    bundle.add(ca)
        return "\n".join(sorted(bundle))

    def push_ca_certs(self) -> None:
        """Push the cert bundle to the container."""
        bundle = self.ca_bundle
        filename = Path(LOCAL_CA_CERTS_PATH / self.bundle_name)
        with open(filename, mode="wt") as f:
            f.write(bundle)

        subprocess.run(["update-ca-certificates", "--fresh"], capture_output=True)

        with open(BUNDLE_PATH) as f:
            self.container.push(BUNDLE_PATH, f, make_dirs=True)

    def clean_ca_certs(self) -> None:
        """Remove the cert bundle from the container."""
        self.container.remove_path(LOCAL_CA_CERTS_PATH / self.bundle_name)

    def _on_certificate_event(
        self, event: Union[CertificateAvailableEvent, CertificateRemovedEvent]
    ) -> None:
        self.push_ca_certs()
        return self.callback_fn(event)
