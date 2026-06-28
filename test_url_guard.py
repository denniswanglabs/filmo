#!/usr/bin/env python3
"""Tests for the SSRF guard (url_guard). Run: python3 -m unittest test_url_guard -v

DNS-dependent: the ALLOW cases resolve real public hostnames (example.com,
stripe.com). The hostname-form-resolving-to-private case monkeypatches
socket.getaddrinfo so it's hermetic and proves the resolved-IP check (not just the
literal-host check) blocks DNS that points at an internal address.
"""
import socket
import unittest

import url_guard


class TestUrlGuardAllow(unittest.TestCase):
    def test_allows_plain_https(self):
        ok, reason = url_guard.is_public_http_url("https://example.com")
        self.assertTrue(ok, reason)

    def test_allows_https_with_path(self):
        ok, reason = url_guard.is_public_http_url("https://stripe.com/pricing")
        self.assertTrue(ok, reason)

    def test_assert_returns_stripped_url(self):
        self.assertEqual(
            url_guard.assert_public_url("  https://example.com  "),
            "https://example.com",
        )


class TestUrlGuardBlock(unittest.TestCase):
    BLOCKED = [
        "http://169.254.169.254/latest/meta-data/",   # AWS/GCP metadata (link-local)
        "http://localhost/",                           # resolves to loopback
        "http://127.0.0.1/",                           # loopback v4
        "http://10.0.0.1/",                            # private 10/8
        "http://192.168.1.1/",                         # private 192.168/16
        "http://[::1]/",                               # loopback v6
        "ftp://example.com",                           # disallowed scheme
        "https://user:pass@example.com",               # embedded credentials
    ]

    def test_blocked_urls(self):
        for u in self.BLOCKED:
            with self.subTest(url=u):
                ok, reason = url_guard.is_public_http_url(u)
                self.assertFalse(ok, "should have been blocked: %s" % u)
                self.assertTrue(reason)

    def test_assert_public_url_raises_on_metadata(self):
        with self.assertRaises(ValueError):
            url_guard.assert_public_url("http://169.254.169.254/latest/meta-data/")

    def test_ipv4_mapped_ipv6_loopback_blocked(self):
        # ::ffff:127.0.0.1 must be unwrapped to v4 and rejected as loopback.
        ok, reason = url_guard.is_public_http_url("http://[::ffff:127.0.0.1]/")
        self.assertFalse(ok, reason)

    def test_hostname_resolving_to_private_is_blocked(self):
        """DNS-rebind-resistant: a public-looking hostname that RESOLVES to a
        private IP must be blocked because we check the resolved addresses."""
        real_getaddrinfo = socket.getaddrinfo

        def fake_getaddrinfo(host, *args, **kwargs):
            if host == "evil.example.com":
                # (family, type, proto, canonname, sockaddr) — sockaddr[0] is the IP
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "",
                         ("127.0.0.1", 0))]
            return real_getaddrinfo(host, *args, **kwargs)

        socket.getaddrinfo = fake_getaddrinfo
        try:
            ok, reason = url_guard.is_public_http_url("https://evil.example.com/")
            self.assertFalse(ok, "hostname resolving to loopback must be blocked")
            self.assertIn("non-public", reason)
            with self.assertRaises(ValueError):
                url_guard.validate_redirect_target("https://evil.example.com/")
        finally:
            socket.getaddrinfo = real_getaddrinfo


if __name__ == "__main__":
    unittest.main(verbosity=2)
