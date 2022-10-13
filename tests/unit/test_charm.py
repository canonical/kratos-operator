# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops.model import ActiveStatus
from ops.testing import Harness

from charm import KratosCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(KratosCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()

    def test_kratos_pebble_ready(self):
        kratos_container_name = "kratos"
        self.harness.set_can_connect(kratos_container_name, True)
        initial_plan = self.harness.get_container_pebble_plan(kratos_container_name)
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        expected_plan = {
            "services": {
                kratos_container_name: {
                    "override": "replace",
                    "summary": "Kratos Operator layer",
                    "startup": "enabled",
                    "command": "kratos serve all --config /etc/config/kratos.yaml",
                    "environment": {
                        "DSN": "postgres://username:password@10.152.183.152:5432/postgres",
                        "COURIER_SMTP_CONNECTION_URI": "smtps://test:test@mailslurper:1025/?skip_ssl_verify=true",
                    },
                }
            }
        }
        container = self.harness.model.unit.get_container(kratos_container_name)
        self.harness.charm.on.kratos_pebble_ready.emit(container)
        updated_plan = self.harness.get_container_pebble_plan(kratos_container_name).to_dict()
        self.assertEqual(expected_plan, updated_plan)

        service = self.harness.model.unit.get_container("kratos").get_service("kratos")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())
