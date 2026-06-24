#!/usr/bin/env python3
"""$0 test: the build subprocess inherits PRODUCER_CONVERSION_READ when requested.

We test the pure env-builder helper, not the HTTP server, so no socket is opened."""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "dashboard"))

import serve


class ConversionFlagEnv(unittest.TestCase):
    def test_flag_set_when_body_requests_it(self):
        env = serve._build_child_env({"conversion_read": True}, mode="mock")
        self.assertEqual(env.get("PRODUCER_CONVERSION_READ"), "1")

    def test_flag_absent_when_not_requested(self):
        env = serve._build_child_env({}, mode="mock")
        self.assertNotIn("PRODUCER_CONVERSION_READ", env)

    def test_mock_still_simulates_paid(self):
        env = serve._build_child_env({}, mode="mock")
        self.assertEqual(env.get("PRODUCER_SIMULATE_PAID"), "1")


if __name__ == "__main__":
    unittest.main()
