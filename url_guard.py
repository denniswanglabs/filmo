#!/usr/bin/env python3
"""SSRF guard — shared allowlist for user-supplied URLs (company_url).

Filmo fetches/scrapes a user-supplied `company_url` in two sinks (brand_extract
`_live_webfetch` and capture_screenshots Playwright). This worker runs on a shared
Railway host, so a user URL pointed at `http://169.254.169.254/...` (cloud metadata),
`http://localhost`, or any internal/private host MUST be refused BEFORE the fetch.

This module is the single source of truth for "is this URL safe to fetch":
  - require an http/https scheme
  - reject embedded credentials (user:pass@host)
  - resolve the hostname via socket.getaddrinfo and reject if ANY resolved address
    is private / loopback / link-local / reserved / multicast / unspecified
    (DNS-rebind-resistant: we check the *resolved* IPs, not just the literal host)
  - explicitly cover 169.254.0.0/16 (AWS/GCP metadata), IPv4-mapped IPv6
    (::ffff:a.b.c.d — unwrapped to v4), IPv6 ULA fc00::/7, link-local fe80::/10, ::1

Fail closed: callers must treat a False/ValueError result as "do not fetch".

stdlib-only (urllib.parse, socket, ipaddress) — no third-party deps so it imports
cleanly in every interpreter the pipeline runs in (including the capture venv).
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = ("http", "https")


def _ip_is_public(ip: ipaddress._BaseAddress) -> tuple[bool, str]:
    """Return (ok, reason). Reject any non-globally-routable address.

    169.254.0.0/16 (and IPv6 fe80::/10) are link-local and already covered by
    `is_link_local`, which is what blocks the cloud-metadata endpoint
    169.254.169.254. IPv4-mapped IPv6 (::ffff:a.b.c.d) is unwrapped to its v4 form
    first so the v4 private/loopback/link-local checks apply.
    """
    # Unwrap IPv4-mapped / 6to4-style IPv6 so the v4 checks below apply.
    if isinstance(ip, ipaddress.IPv6Address):
        mapped = getattr(ip, "ipv4_mapped", None)
        if mapped is not None:
            ip = mapped
        elif getattr(ip, "sixtofour", None) is not None:
            ip = ip.sixtofour

    if ip.is_loopback:
        return False, f"loopback address ({ip})"
    if ip.is_link_local:                       # 169.254.0.0/16, fe80::/10 (metadata)
        return False, f"link-local address ({ip})"
    if ip.is_private:                          # 10/8, 172.16/12, 192.168/16, fc00::/7
        return False, f"private address ({ip})"
    if ip.is_unspecified:                      # 0.0.0.0, ::
        return False, f"unspecified address ({ip})"
    if ip.is_multicast:
        return False, f"multicast address ({ip})"
    if ip.is_reserved:
        return False, f"reserved address ({ip})"
    return True, ""


def is_public_http_url(url: str) -> tuple[bool, str]:
    """Return (ok, reason). ok=True only when `url` is safe to fetch.

    A True result means: http/https scheme, no embedded credentials, and EVERY
    address the hostname resolves to is globally routable (public). reason is ""
    on success and a human-readable explanation on failure.
    """
    u = (url or "").strip()
    if not u:
        return False, "empty URL"

    try:
        parts = urlsplit(u)
    except Exception as e:
        return False, f"unparseable URL ({e})"

    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        return False, f"scheme {scheme!r} not allowed (only http/https)"

    # Embedded credentials (user:pass@host) are a classic SSRF/obfuscation vector.
    if parts.username or parts.password or ("@" in (parts.netloc or "")):
        return False, "embedded credentials in URL are not allowed"

    host = parts.hostname  # lowercased, brackets stripped for IPv6 literals
    if not host:
        return False, "URL has no host"

    # If the host is a bare IP literal, check it directly (getaddrinfo would too,
    # but this gives a precise reason and avoids a needless lookup).
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        ok, reason = _ip_is_public(literal)
        if not ok:
            return False, f"host {host} is a non-public IP: {reason}"
        return True, ""

    # Hostname: resolve and reject if ANY resolved address is non-public. Checking
    # the resolved IPs (not just the literal host) is what makes this resistant to
    # a hostname that points at an internal IP (incl. DNS-rebind setups).
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        return False, f"hostname {host!r} did not resolve ({e})"
    except Exception as e:
        return False, f"hostname {host!r} resolution failed ({e})"

    if not infos:
        return False, f"hostname {host!r} resolved to no addresses"

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            return False, f"hostname {host!r} resolved to unparseable address {ip_str!r}"
        ok, reason = _ip_is_public(ip)
        if not ok:
            return False, f"hostname {host!r} resolves to non-public {reason}"

    return True, ""


def assert_public_url(url: str) -> str:
    """Raise ValueError if `url` is not a safe-to-fetch public http/https URL.

    Returns the (stripped) URL on success so callers can use the validated value.
    """
    ok, reason = is_public_http_url(url)
    if not ok:
        raise ValueError(f"refusing to fetch unsafe URL {url!r}: {reason}")
    return (url or "").strip()


def validate_redirect_target(url: str) -> str:
    """Per-hop redirect re-validation. Same checks as assert_public_url.

    Use on each redirect target so a public URL that 30x-redirects to an internal
    host (e.g. 169.254.169.254) is refused mid-chain. Raises ValueError if unsafe.
    """
    ok, reason = is_public_http_url(url)
    if not ok:
        raise ValueError(f"refusing to follow redirect to unsafe URL {url!r}: {reason}")
    return (url or "").strip()
