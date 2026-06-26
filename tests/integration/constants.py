# Copyright 2025 Canonical Ltd.
# See LICENSE file for licensing details.

from pathlib import Path

import yaml

METADATA = yaml.safe_load(Path("./charmcraft.yaml").read_text())
KRATOS_APP = METADATA["name"]
KRATOS_IMAGE = METADATA["resources"]["oci-image"]["upstream-source"]
ISTIO_K8S_CHARM = "istio-k8s"
ISTIO_INGRESS_K8S_CHARM = "istio-ingress-k8s"
ISTIO_K8S_APP = "istio"
ISTIO_PUBLIC_APP = "istio-public"
ISTIO_INTERNAL_APP = "istio-internal"
ISTIO_CHANNEL = "2/stable"
DB_APP = "postgresql-k8s"
CA_APP = "self-signed-certificates"
LOGIN_UI_APP = "identity-platform-login-ui-operator"
ADMIN_EMAIL = "admin1@adminmail.com"
ADMIN_PASSWORD = "admin"
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
