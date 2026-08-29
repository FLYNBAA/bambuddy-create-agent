"""Network destination validation for provider-returned artifact URLs."""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Mapping
from typing import Literal
from urllib.parse import urlsplit
from urllib.request import getproxies


_PROXY_ENVIRONMENT_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)

def environment_proxy_configured(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Detect environment variables or the operating-system proxy settings."""
    source = os.environ if environ is None else environ
    if any(
        isinstance(source.get(name), str) and bool(source[name].strip())
        for name in _PROXY_ENVIRONMENT_VARIABLES
    ):
        return True
    if environ is not None:
        return False
    return configured_system_proxy_url() is not None

def configured_system_proxy_url() -> str | None:
    """Return a usable HTTPS/HTTP proxy without exposing it to responses or logs."""
    proxies = getproxies()
    for name in ("https", "all", "http"):
        value = proxies.get(name)
        if not isinstance(value, str) or not value.strip():
            continue
        normalized = value.strip()
        parsed = urlsplit(normalized)
        if parsed.scheme in {"http", "https", "socks5", "socks5h"} and parsed.hostname:
            return normalized
    for port in (7890, 7891, 7892):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.15):
                return f"http://127.0.0.1:{port}"
        except OSError:
            continue
    return None


def httpx_route_kwargs(use_proxy: bool) -> dict[str, object]:
    """Build HTTPX routing arguments for direct, environment, or Windows proxy use."""
    if not use_proxy:
        return {"trust_env": False}
    if any(
        isinstance(os.environ.get(name), str) and bool(os.environ[name].strip())
        for name in _PROXY_ENVIRONMENT_VARIABLES
    ):
        return {"trust_env": True}
    proxy = configured_system_proxy_url()
    return {"trust_env": False, "proxy": proxy} if proxy else {"trust_env": True}

ProxyMode = Literal["auto", "direct", "environment"]


def proxy_route_candidates(
    mode: ProxyMode,
    environ: Mapping[str, str] | None = None,
) -> tuple[bool, ...]:
    """Return HTTPX trust_env routes in deterministic failover order."""
    if mode == "direct":
        return (False,)
    if mode == "environment":
        return (True,)
    if mode != "auto":
        raise ValueError("Proxy mode must be auto, direct, or environment")
    return (False, True) if environment_proxy_configured(environ) else (False,)

class UnsafeRemoteURL(ValueError):
    """Raised when a remote artifact URL could reach a non-public network."""


def resolve_public_http_addresses(url: str) -> tuple[str, ...]:
    """Resolve an HTTP(S) URL once and return only globally routable addresses."""
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeRemoteURL("Artifact URL must be an absolute HTTP(S) URL")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeRemoteURL("Artifact URL must not contain credentials")

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as error:
        raise UnsafeRemoteURL("Artifact URL contains an invalid port") from error

    try:
        addresses = socket.getaddrinfo(
            parsed.hostname,
            port,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as error:
        raise UnsafeRemoteURL("Artifact host could not be resolved") from error
    if not addresses:
        raise UnsafeRemoteURL("Artifact host did not resolve to an address")

    public_addresses: list[str] = []
    for address in addresses:
        raw_address = address[4][0].split("%", 1)[0]
        try:
            resolved = ipaddress.ip_address(raw_address)
        except ValueError as error:
            raise UnsafeRemoteURL("Artifact host resolved to an invalid address") from error
        if not resolved.is_global:
            raise UnsafeRemoteURL("Artifact URL resolves to a non-public address")
        normalized = str(resolved)
        if normalized not in public_addresses:
            public_addresses.append(normalized)
    return tuple(public_addresses)


def assert_public_http_url(url: str) -> None:
    """Reject credentials, non-HTTP schemes, and any non-public resolved address."""
    resolve_public_http_addresses(url)


def assert_allowed_https_host(url: str, allowed_suffixes: tuple[str, ...]) -> None:
    """Accept only HTTPS URLs under explicitly trusted provider-owned domains."""
    parsed = urlsplit(url)
    hostname = (parsed.hostname or "").rstrip(".").lower()
    allowed = tuple(suffix.rstrip(".").lower() for suffix in allowed_suffixes)
    if parsed.scheme != "https" or not hostname:
        raise UnsafeRemoteURL("Artifact URL must use HTTPS")
    if not any(hostname == suffix or hostname.endswith(f".{suffix}") for suffix in allowed):
        raise UnsafeRemoteURL("Artifact URL host is not an approved provider domain")
    assert_public_http_url(url)
