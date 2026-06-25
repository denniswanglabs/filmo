#!/usr/bin/env python3
"""$0, no-network, no-sandbox unit tests for the CAPTURE_BACKEND=nemoclaw switch
and the per-job dynamic egress-allowlist policy file.

Everything that would touch the real NemoClaw sandbox is mocked at the
`_nemoclaw_*` seams, so these run anywhere (no Docker, no nemoclaw CLI). They
assert:
  - flag-off (default) is byte-identical: capture_url NEVER touches nemoclaw and
    routes to the native _capture_inproc path.
  - flag-on + preflight failure falls back cleanly to native.
  - flag-on + successful sandbox capture returns the sandbox manifest.
  - the generated policy-file content allows ONLY the target host (+ apex +
    *.apex) + the curated asset CDNs, as raw `access: full, tls: skip` tunnels —
    NOT open egress.
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import capture_screenshots as cs


class TestCaptureBackendSwitch(unittest.TestCase):
    def setUp(self):
        # Ensure a clean env per test (CAPTURE_BACKEND must not leak between them).
        self._saved = os.environ.pop("CAPTURE_BACKEND", None)

    def tearDown(self):
        os.environ.pop("CAPTURE_BACKEND", None)
        if self._saved is not None:
            os.environ["CAPTURE_BACKEND"] = self._saved

    def test_flag_off_never_touches_nemoclaw_and_uses_native(self):
        """Default (no CAPTURE_BACKEND): _capture_via_nemoclaw is NEVER called;
        capture_url routes straight to the native in-process path."""
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(cs, "_capture_via_nemoclaw") as m_nc, \
                 mock.patch.object(cs, "_have_playwright", return_value=True), \
                 mock.patch.object(cs, "_capture_inproc",
                                   return_value={"ok": True, "shots": [{"x": 1}],
                                                 "url": "https://x.com"}) as m_native:
                out = cs.capture_url("https://x.com", d)
        m_nc.assert_not_called()
        m_native.assert_called_once()
        self.assertEqual(out["shots"], [{"x": 1}])

    def test_flag_off_with_explicit_native_value(self):
        """CAPTURE_BACKEND=native is also a no-op for the sandbox path."""
        os.environ["CAPTURE_BACKEND"] = "native"
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(cs, "_capture_via_nemoclaw") as m_nc, \
                 mock.patch.object(cs, "_have_playwright", return_value=True), \
                 mock.patch.object(cs, "_capture_inproc",
                                   return_value={"ok": True, "shots": [1]}):
                cs.capture_url("https://x.com", d)
        m_nc.assert_not_called()

    def test_flag_on_preflight_fail_falls_back_to_native(self):
        """CAPTURE_BACKEND=nemoclaw but the sandbox path returns None (any
        preflight/capture failure) -> capture_url falls back to native and
        returns the native manifest."""
        os.environ["CAPTURE_BACKEND"] = "nemoclaw"
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(cs, "_capture_via_nemoclaw",
                                   return_value=None) as m_nc, \
                 mock.patch.object(cs, "_have_playwright", return_value=True), \
                 mock.patch.object(cs, "_capture_inproc",
                                   return_value={"ok": True, "shots": ["native"],
                                                 "url": "https://x.com"}) as m_native:
                out = cs.capture_url("https://x.com", d)
        m_nc.assert_called_once()
        m_native.assert_called_once()
        self.assertEqual(out["shots"], ["native"])

    def test_flag_on_success_returns_sandbox_manifest(self):
        """CAPTURE_BACKEND=nemoclaw and the sandbox capture succeeds -> its
        manifest is returned and native is NOT invoked."""
        os.environ["CAPTURE_BACKEND"] = "nemoclaw"
        sandbox_manifest = {"ok": True, "backend": "nemoclaw",
                            "shots": [{"backend": "nemoclaw"}],
                            "url": "https://x.com", "count": 1}
        with tempfile.TemporaryDirectory() as d:
            with mock.patch.object(cs, "_capture_via_nemoclaw",
                                   return_value=sandbox_manifest) as m_nc, \
                 mock.patch.object(cs, "_capture_inproc") as m_native:
                out = cs.capture_url("https://x.com", d)
        m_nc.assert_called_once()
        m_native.assert_not_called()
        self.assertEqual(out["backend"], "nemoclaw")


class TestPreflightFallback(unittest.TestCase):
    """_nemoclaw_preflight short-circuits to False on each failed step so the
    sandbox is never a hard dependency."""

    def test_preflight_false_when_status_not_ready(self):
        not_ready = mock.Mock(returncode=0, stdout="Phase: Pending", stderr="")
        with mock.patch.object(cs, "_nemoclaw_exec", return_value=not_ready):
            self.assertFalse(cs._nemoclaw_preflight("docs.stripe.com"))

    def test_preflight_false_when_chromium_missing_and_install_fails(self):
        ready = mock.Mock(returncode=0, stdout="Phase: Ready\n", stderr="")
        with mock.patch.object(cs, "_nemoclaw_exec", return_value=ready), \
             mock.patch.object(cs, "_nemoclaw_chromium_ready", return_value=False), \
             mock.patch.object(cs, "_nemoclaw_install_chromium", return_value=False):
            self.assertFalse(cs._nemoclaw_preflight("docs.stripe.com"))

    def test_preflight_false_when_allowlist_fails(self):
        ready = mock.Mock(returncode=0, stdout="Phase: Ready\n", stderr="")
        with mock.patch.object(cs, "_nemoclaw_exec", return_value=ready), \
             mock.patch.object(cs, "_nemoclaw_chromium_ready", return_value=True), \
             mock.patch.object(cs, "_nemoclaw_allow_host", return_value=False):
            self.assertFalse(cs._nemoclaw_preflight("notion.so"))

    def test_preflight_true_full_happy_path(self):
        ready = mock.Mock(returncode=0, stdout="Phase: Ready\n", stderr="")
        with mock.patch.object(cs, "_nemoclaw_exec", return_value=ready), \
             mock.patch.object(cs, "_nemoclaw_chromium_ready", return_value=True), \
             mock.patch.object(cs, "_nemoclaw_allow_host", return_value=True):
            self.assertTrue(cs._nemoclaw_preflight("docs.stripe.com"))


class TestDynamicPolicyFile(unittest.TestCase):
    def test_policy_yaml_allows_target_apex_and_curated_assets_only(self):
        doc = cs._nemoclaw_policy_yaml("app.notion.so")
        # target + apex + *.apex present
        self.assertIn('host: "app.notion.so"', doc)
        self.assertIn('host: "notion.so"', doc)
        self.assertIn('host: "*.notion.so"', doc)
        # curated asset CDNs present
        for h in cs._NEMOCLAW_ASSET_HOSTS:
            self.assertIn('host: "%s"' % h, doc)
        # demo-targets shape: access: full, NO tls: skip (the proxy TLS-
        # terminates; tls: skip was rejected as "Policy unchanged"). Not open
        # egress, no wildcard-everything.
        self.assertIn("access: full", doc)
        self.assertNotIn("tls: skip", doc)
        self.assertNotIn('host: "*"', doc)
        self.assertNotIn("0.0.0.0", doc)
        # is a valid preset doc shape
        self.assertIn("preset:", doc)
        self.assertIn("network_policies:", doc)

    def test_policy_yaml_apex_host_has_no_redundant_apex(self):
        """An apex target (notion.so) gets the apex once + the *.apex wildcard,
        with no duplicate bare apex entry."""
        doc = cs._nemoclaw_policy_yaml("notion.so")
        self.assertEqual(doc.count('host: "notion.so"'), 1)
        # apex target: _host_apex returns None, so no '*.notion.so' wildcard is added.
        self.assertNotIn('host: "*.notion.so"', doc)

    def test_allow_host_skips_policy_add_when_already_reachable(self):
        """If the host is already reachable, _nemoclaw_allow_host returns True
        WITHOUT writing/applying a policy (no policy-add call)."""
        with mock.patch.object(cs, "_nemoclaw_host_allowed", return_value=True), \
             mock.patch.object(cs, "_nemoclaw_exec") as m_exec:
            self.assertTrue(cs._nemoclaw_allow_host("docs.stripe.com"))
        # policy-add must NOT have been called
        for call in m_exec.call_args_list:
            self.assertNotIn("policy-add", call.args[0])

    def test_allow_host_applies_policy_when_not_reachable(self):
        """If not reachable: write+apply policy, then re-probe; True iff egress
        opened. Verify policy-add --from-file --yes is invoked with a real file."""
        probe_results = [False, True]  # first probe fails, post-add probe passes

        def fake_allowed(host, **kw):
            return probe_results.pop(0)

        applied = {"file": None}

        def fake_exec(args, **kw):
            if args[0] == "policy-add":
                # args == ["policy-add","--from-file",<path>,"--yes"]
                self.assertEqual(args[1], "--from-file")
                self.assertEqual(args[3], "--yes")
                applied["file"] = args[2]
                # the file must exist and contain the target host at apply time
                with open(args[2], encoding="utf-8") as fh:
                    body = fh.read()
                self.assertIn("notion.so", body)
                return mock.Mock(returncode=0, stdout="applied", stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(cs, "_nemoclaw_host_allowed", side_effect=fake_allowed), \
             mock.patch.object(cs, "_nemoclaw_exec", side_effect=fake_exec):
            self.assertTrue(cs._nemoclaw_allow_host("app.notion.so"))
        self.assertIsNotNone(applied["file"])
        # temp policy file is cleaned up
        self.assertFalse(os.path.exists(applied["file"]))

    def test_allow_host_false_when_policy_add_fails(self):
        with mock.patch.object(cs, "_nemoclaw_host_allowed", return_value=False), \
             mock.patch.object(cs, "_nemoclaw_exec",
                               return_value=mock.Mock(returncode=1, stdout="",
                                                      stderr="policy_denied")):
            self.assertFalse(cs._nemoclaw_allow_host("app.notion.so"))


class TestHostApex(unittest.TestCase):
    def test_subdomain_apex(self):
        self.assertEqual(cs._host_apex("app.notion.so"), "notion.so")
        self.assertEqual(cs._host_apex("docs.stripe.com"), "stripe.com")

    def test_apex_returns_none(self):
        self.assertIsNone(cs._host_apex("notion.so"))
        self.assertIsNone(cs._host_apex("stripe.com"))


class TestCapturePythonAndShquote(unittest.TestCase):
    def test_capture_python_is_valid_python_source(self):
        """The capture body injected into the sandbox must itself be valid
        Python (so a syntax error never silently fails the on-camera capture)."""
        import ast
        body = cs._nemoclaw_capture_python("https://docs.stripe.com/", "/tmp/cap-01.png")
        ast.parse(body)  # raises SyntaxError if malformed
        self.assertIn("CAPTURE_OK", body)
        self.assertIn("--ignore-certificate-errors", body)
        self.assertIn("NetworkService,NetworkServiceInProcess", body)
        # URL is JSON-encoded (safely quoted) inside the source
        self.assertIn('"https://docs.stripe.com/"', body)

    def test_shquote_roundtrips_single_quotes(self):
        s = "a'b'c"
        q = cs._shquote(s)
        self.assertTrue(q.startswith("'") and q.endswith("'"))
        # POSIX-correct escaped single quote sequence
        self.assertIn("'\\''", q)


if __name__ == "__main__":
    unittest.main()
