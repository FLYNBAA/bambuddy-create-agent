"""Focused contract tests for safe, complete Bambu printer subnet scans."""

import asyncio

import pytest

from backend.app.services.discovery import (
    MAX_CONCURRENT_PROBES,
    SubnetScanner,
    parse_configured_discovery_subnets,
    validate_scan_subnet,
    validate_scan_timeout,
)


def test_validate_scan_subnet_normalizes_private_cidr():
    assert validate_scan_subnet("192.168.10.7/24") == "192.168.10.0/24"
    assert validate_scan_subnet("100.64.0.8/30") == "100.64.0.8/30"


@pytest.mark.parametrize("subnet", ["8.8.8.0/24", "2001:db8::/64", "10.0.0.0/8", "not-a-cidr"])
def test_validate_scan_subnet_rejects_unsafe_or_unbounded_ranges(subnet: str):
    with pytest.raises(ValueError):
        validate_scan_subnet(subnet)


@pytest.mark.parametrize("timeout", [0, 0.01, 10.1, float("inf"), float("nan")])
def test_validate_scan_timeout_rejects_unsafe_values(timeout: float):
    with pytest.raises(ValueError):
        validate_scan_timeout(timeout)


def test_parse_configured_discovery_subnets_keeps_only_safe_unique_candidates():
    configured = parse_configured_discovery_subnets(
        "192.168.20.12/24, invalid, 10.2.0.0/24, 192.168.20.0/24, 8.8.8.0/24"
    )

    assert configured == ["192.168.20.0/24", "10.2.0.0/24"]


@pytest.mark.asyncio
async def test_scanner_visits_every_usable_host_without_unbounded_parallelism(monkeypatch):
    scanner = SubnetScanner()
    probed: list[str] = []
    active = 0
    peak_active = 0

    async def probe(ip: str, _timeout: float) -> None:
        nonlocal active, peak_active
        active += 1
        peak_active = max(peak_active, active)
        probed.append(ip)
        await asyncio.sleep(0)
        active -= 1

    monkeypatch.setattr(scanner, "_probe_host", probe)

    await scanner.scan_subnet("192.168.20.0/23", timeout=0.1)

    assert len(probed) == len(set(probed))
    assert {"192.168.20.1", "192.168.21.254"}.issubset(probed)
    assert scanner.progress == (510, 510)
    assert peak_active <= MAX_CONCURRENT_PROBES


@pytest.mark.asyncio
async def test_stop_cancels_inflight_scan_window(monkeypatch):
    scanner = SubnetScanner()
    probe_started = asyncio.Event()
    never_complete = asyncio.Event()

    async def probe(_ip: str, _timeout: float) -> None:
        probe_started.set()
        await never_complete.wait()

    monkeypatch.setattr(scanner, "_probe_host", probe)
    scan_task = asyncio.create_task(scanner.scan_subnet("192.168.30.0/24", timeout=0.1))
    await probe_started.wait()

    scanner.stop()

    with pytest.raises(asyncio.CancelledError):
        await scan_task
    assert scanner.is_running is False
