# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.

import unittest

from ops.testing import Harness

from charm import KratosCharm


class TestCharm(unittest.TestCase):
    def setUp(self):
        self.harness = Harness(KratosCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin()
