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
        """LEGACY policy-add mode: if not reachable, write+apply policy, then
        re-probe; True iff egress opened. Verify policy-add --from-file --yes is
        invoked with a real file."""
        os.environ["NEMOCLAW_EGRESS_MODE"] = "policy-add"
        self.addCleanup(os.environ.pop, "NEMOCLAW_EGRESS_MODE", None)
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
        os.environ["NEMOCLAW_EGRESS_MODE"] = "policy-add"
        self.addCleanup(os.environ.pop, "NEMOCLAW_EGRESS_MODE", None)
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


class TestInjectHostsIntoDemoTargets(unittest.TestCase):
    """Pure string-level injection of allowed hosts into the live policy's
    `demo-targets` preset (the only preset whose `access: full` shape the live
    egress proxy actually honours after a `policy set` full-replace)."""

    SAMPLE = (
        "version: 1\n"
        "network_policies:\n"
        "  demo-targets:\n"
        "    name: demo-targets\n"
        "    endpoints:\n"
        "    - host: docs.stripe.com\n"
        "      port: 443\n"
        "      access: full\n"
        "    binaries:\n"
        "    - path: /**\n"
        "  other:\n"
        "    name: other\n"
        "    endpoints:\n"
        "    - host: example.org\n"
        "      port: 443\n"
        "      access: full\n"
    )

    def test_injects_hosts_at_top_of_demo_targets_endpoints(self):
        out = cs._nemoclaw_inject_hosts(self.SAMPLE, ["app.notion.so", "notion.so"])
        # new hosts appear inside demo-targets (single-quoted), before existing
        self.assertIn("host: 'app.notion.so'", out)
        self.assertIn("host: 'notion.so'", out)
        di = out.index("demo-targets:")
        oi = out.index("other:")
        # both injected hosts land inside the demo-targets block (before "other:")
        self.assertLess(out.index("host: 'app.notion.so'"), oi)
        self.assertGreater(out.index("host: 'app.notion.so'"), di)
        # the pre-existing stripe endpoint is preserved
        self.assertIn("host: docs.stripe.com", out)
        # the OTHER preset is untouched
        self.assertIn("host: example.org", out)

    def test_wildcard_host_is_quoted_not_alias(self):
        """A *.apex wildcard must be single-quoted; bare '*' is a YAML alias and
        the gateway rejects it ('did not find ... alias')."""
        out = cs._nemoclaw_inject_hosts(self.SAMPLE, ["*.notion.so"])
        self.assertIn("host: '*.notion.so'", out)
        # never the bare/alias form
        self.assertNotIn("host: *.notion.so", out)

    def test_uses_working_shape_no_tls_skip(self):
        out = cs._nemoclaw_inject_hosts(self.SAMPLE, ["example.com"])
        # injected entries use access: full and NEVER tls: skip (the live proxy
        # only honours the demo-targets full-terminate shape)
        self.assertIn("host: 'example.com'\n      port: 443\n      access: full", out)
        self.assertNotIn("tls: skip", out)

    def test_skips_hosts_already_present(self):
        out = cs._nemoclaw_inject_hosts(self.SAMPLE, ["docs.stripe.com"])
        # no duplicate stripe endpoint (existing unquoted entry counts)
        self.assertEqual(out.count("docs.stripe.com"), 1)

    def test_raises_when_no_demo_targets_preset(self):
        with self.assertRaises(ValueError):
            cs._nemoclaw_inject_hosts("version: 1\nnetwork_policies:\n  x:\n    name: x\n", ["a.com"])


class TestAllowHostViaPolicySet(unittest.TestCase):
    """The reworked _nemoclaw_allow_host: when a host is blocked it fetches the
    LIVE policy via `openshell policy get --full`, injects the target + curated
    asset hosts into demo-targets, applies via `openshell policy set --wait`,
    then re-probes. Only `policy set` (full replace) reprograms the live proxy;
    `policy-add`/`policy update` do not."""

    def setUp(self):
        os.environ["NEMOCLAW_EGRESS_MODE"] = "policy-set"

    def tearDown(self):
        os.environ.pop("NEMOCLAW_EGRESS_MODE", None)

    def test_skips_when_already_reachable(self):
        with mock.patch.object(cs, "_nemoclaw_host_allowed", return_value=True), \
             mock.patch.object(cs, "_openshell_exec") as m_os:
            self.assertTrue(cs._nemoclaw_allow_host("docs.stripe.com"))
        m_os.assert_not_called()

    def test_policy_set_path_applies_and_reprobes(self):
        probe = [False, True]  # blocked, then open after policy set

        def fake_allowed(host, **kw):
            return probe.pop(0)

        live = TestInjectHostsIntoDemoTargets.SAMPLE
        applied = {"policy_path": None}

        def fake_os(args, **kw):
            if args and args[0] == "policy" and args[1] == "get":
                return mock.Mock(returncode=0,
                                 stdout="Version: 36\n---\n" + live, stderr="")
            if args and args[0] == "policy" and args[1] == "set":
                # locate --policy <path> and verify it contains the target
                i = args.index("--policy")
                applied["policy_path"] = args[i + 1]
                with open(args[i + 1], encoding="utf-8") as fh:
                    body = fh.read()
                self.assertIn("notion.so", body)
                self.assertNotIn("tls: skip", body)
                return mock.Mock(returncode=0,
                                 stdout="Policy version 40 loaded (active version: 40)",
                                 stderr="")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(cs, "_nemoclaw_host_allowed", side_effect=fake_allowed), \
             mock.patch.object(cs, "_openshell_exec", side_effect=fake_os):
            self.assertTrue(cs._nemoclaw_allow_host("app.notion.so"))
        self.assertIsNotNone(applied["policy_path"])
        self.assertFalse(os.path.exists(applied["policy_path"]))  # temp cleaned up

    def test_false_when_policy_set_fails(self):
        live = TestInjectHostsIntoDemoTargets.SAMPLE

        def fake_os(args, **kw):
            if args and args[1] == "get":
                return mock.Mock(returncode=0, stdout="---\n" + live, stderr="")
            if args and args[1] == "set":
                return mock.Mock(returncode=1, stdout="", stderr="denied")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with mock.patch.object(cs, "_nemoclaw_host_allowed", return_value=False), \
             mock.patch.object(cs, "_openshell_exec", side_effect=fake_os):
            self.assertFalse(cs._nemoclaw_allow_host("app.notion.so"))

    def test_false_when_policy_get_fails(self):
        def fake_os(args, **kw):
            return mock.Mock(returncode=1, stdout="", stderr="no sandbox")

        with mock.patch.object(cs, "_nemoclaw_host_allowed", return_value=False), \
             mock.patch.object(cs, "_openshell_exec", side_effect=fake_os):
            self.assertFalse(cs._nemoclaw_allow_host("app.notion.so"))

    def test_re_probe_gates_success_even_if_set_reports_ok(self):
        """policy set returns rc=0 but egress still blocked -> overall False
        (the safety gate: we only claim success when curl actually opens)."""
        live = TestInjectHostsIntoDemoTargets.SAMPLE

        def fake_os(args, **kw):
            if args[1] == "get":
                return mock.Mock(returncode=0, stdout="---\n" + live, stderr="")
            return mock.Mock(returncode=0, stdout="loaded", stderr="")

        with mock.patch.object(cs, "_nemoclaw_host_allowed", return_value=False), \
             mock.patch.object(cs, "_openshell_exec", side_effect=fake_os):
            self.assertFalse(cs._nemoclaw_allow_host("app.notion.so"))


if __name__ == "__main__":
    unittest.main()
