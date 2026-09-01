"""
Bambu Lab printer discovery service using SSDP and subnet scanning.

Bambu Lab printers advertise themselves via SSDP (Simple Service Discovery Protocol)
on the local network. This service listens for these advertisements and provides
a list of discovered printers.

For Docker environments where SSDP multicast doesn't work, subnet scanning is
available as an alternative discovery method.
"""

import asyncio
import ipaddress
import logging
import math
import os
import re
import socket
import struct
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# A scan is an explicit operator action. Limit it to private address space that
# can contain printers, including Tailscale's CGNAT range for routed networks.
# The ceiling is deliberately much higher than the old /22 truncation while
# still preventing one request from scheduling an unbounded Internet scan.
_DISCOVERY_ADDRESS_RANGES = (
    ipaddress.IPv4Network("10.0.0.0/8"),
    ipaddress.IPv4Network("100.64.0.0/10"),
    ipaddress.IPv4Network("172.16.0.0/12"),
    ipaddress.IPv4Network("192.168.0.0/16"),
)
MAX_SCAN_HOSTS = 65_534
MAX_CONCURRENT_PROBES = 64
MIN_SCAN_TIMEOUT = 0.1
MAX_SCAN_TIMEOUT = 10.0
MAX_CONFIGURED_DISCOVERY_SUBNETS = 16


def _host_count(network: ipaddress.IPv4Network) -> int:
    """Return the number of addresses yielded by ``IPv4Network.hosts``."""
    if network.prefixlen >= 31:
        return network.num_addresses
    return network.num_addresses - 2


def validate_scan_subnet(subnet: str) -> str:
    """Normalize one safe, bounded IPv4 printer-discovery CIDR."""
    try:
        network = ipaddress.ip_network(subnet.strip(), strict=False)
    except (AttributeError, ValueError) as exc:
        raise ValueError("subnet must be an IPv4 CIDR") from exc

    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError("subnet must be an IPv4 CIDR")
    if not any(network.subnet_of(allowed) for allowed in _DISCOVERY_ADDRESS_RANGES):
        raise ValueError("subnet must be within a private or Tailscale CGNAT range")

    host_count = _host_count(network)
    if host_count > MAX_SCAN_HOSTS:
        raise ValueError(f"subnet contains more than {MAX_SCAN_HOSTS} usable hosts")
    return str(network)


def validate_scan_timeout(timeout: float) -> float:
    """Validate the per-host probe timeout before work is scheduled."""
    try:
        value = float(timeout)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be a number") from exc
    if not math.isfinite(value) or not MIN_SCAN_TIMEOUT <= value <= MAX_SCAN_TIMEOUT:
        raise ValueError(f"timeout must be between {MIN_SCAN_TIMEOUT} and {MAX_SCAN_TIMEOUT} seconds")
    return value


def parse_configured_discovery_subnets(value: str | None = None) -> list[str]:
    """Parse valid bridge-mode discovery candidates from ``BCA_DISCOVERY_SUBNETS``.

    Invalid entries are ignored rather than making application startup depend on
    a deployment typo. Request-provided CIDRs use ``validate_scan_subnet`` and
    are rejected to the caller instead.
    """
    configured = os.environ.get("BCA_DISCOVERY_SUBNETS", "") if value is None else value
    subnets: list[str] = []
    for candidate in configured.split(","):
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            subnet = validate_scan_subnet(candidate)
        except ValueError as exc:
            logger.warning("Ignoring unsafe BCA_DISCOVERY_SUBNETS entry %r: %s", candidate, exc)
            continue
        if subnet not in subnets:
            subnets.append(subnet)
        if len(subnets) >= MAX_CONFIGURED_DISCOVERY_SUBNETS:
            logger.warning("Ignoring BCA_DISCOVERY_SUBNETS entries after the first %s", MAX_CONFIGURED_DISCOVERY_SUBNETS)
            break
    return subnets


def is_running_in_docker() -> bool:
    """Detect if we're running inside a Docker container."""
    # Check for .dockerenv file
    if Path("/.dockerenv").exists():
        return True

    # Check cgroup for docker/containerd
    try:
        with open("/proc/1/cgroup") as f:
            content = f.read()
            if "docker" in content or "containerd" in content or "kubepods" in content:
                return True
    except (FileNotFoundError, PermissionError):
        pass  # /proc/1/cgroup may not exist or be readable; fall through to env check

    # Check for container environment variable
    return bool(os.environ.get("CONTAINER") or os.environ.get("DOCKER_CONTAINER"))


# SSDP multicast address - Bambu uses port 2021, not standard 1900
SSDP_ADDR = "239.255.255.250"
SSDP_PORT = 2021  # Bambu Lab uses non-standard port

# Bambu Lab SSDP search target
BAMBU_SEARCH_TARGET = "urn:bambulab-com:device:3dprinter:1"

# Virtual printer serial suffix to exclude from discovery (Bambuddy's own virtual printer)
# All virtual printer serials end with this suffix, regardless of model
VIRTUAL_PRINTER_SERIAL_SUFFIX = "391800001"

# SSDP M-SEARCH message
SSDP_MSEARCH = (
    "M-SEARCH * HTTP/1.1\r\n"
    f"HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n"
    'MAN: "ssdp:discover"\r\n'
    "MX: 3\r\n"
    f"ST: {BAMBU_SEARCH_TARGET}\r\n"
    "\r\n"
)


@dataclass
class DiscoveredPrinter:
    """Represents a discovered Bambu Lab printer."""

    serial: str
    name: str
    ip_address: str
    model: str | None = None
    discovered_at: str | None = None

    def to_dict(self) -> dict:
        return {
            "serial": self.serial,
            "name": self.name,
            "ip_address": self.ip_address,
            "model": self.model,
            "discovered_at": self.discovered_at,
        }


class PrinterDiscoveryService:
    """Service for discovering Bambu Lab printers on the network."""

    def __init__(self):
        self._discovered: dict[str, DiscoveredPrinter] = {}
        self._running = False
        self._task: asyncio.Task | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def discovered_printers(self) -> list[DiscoveredPrinter]:
        return list(self._discovered.values())

    def clear(self):
        """Clear discovered printers."""
        self._discovered.clear()

    async def start(self, duration: float = 10.0):
        """Start discovery for a specified duration."""
        if self._running:
            return

        self._running = True
        self._discovered.clear()
        self._task = asyncio.create_task(self._discover(duration))

    async def stop(self):
        """Stop discovery."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # Expected when cancelling the discovery task
        self._task = None

    async def _discover(self, duration: float):
        """Run discovery for the specified duration.

        Bambu printers broadcast NOTIFY messages periodically on port 2021.
        We need to bind to that port and listen for broadcasts.
        """
        sock = None
        try:
            # Create UDP socket for SSDP
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # Try to set SO_REUSEPORT if available (Linux/macOS)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except (AttributeError, OSError):
                pass  # SO_REUSEPORT not available on all platforms; non-critical

            # Set non-blocking mode
            sock.setblocking(False)

            # Bind to the SSDP port to receive NOTIFY broadcasts from printers
            sock.bind(("", SSDP_PORT))

            # Join multicast group to receive multicast messages
            mreq = struct.pack("4sl", socket.inet_aton(SSDP_ADDR), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

            # Enable broadcast
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            logger.info("Starting SSDP discovery on port %s for Bambu Lab printers...", SSDP_PORT)

            # Send initial M-SEARCH request to trigger responses
            try:
                sock.sendto(SSDP_MSEARCH.encode(), (SSDP_ADDR, SSDP_PORT))
            except OSError as e:
                logger.debug("M-SEARCH send error: %s", e)

            start_time = asyncio.get_event_loop().time()
            last_send = start_time

            while self._running and (asyncio.get_event_loop().time() - start_time) < duration:
                # Try to receive data
                try:
                    data, addr = sock.recvfrom(4096)
                    message = data.decode("utf-8", errors="ignore")
                    logger.debug("Received from %s: %s...", addr[0], message[:100])
                    self._handle_response(message, addr[0])
                except BlockingIOError:
                    # No data available, that's fine
                    pass
                except OSError as e:
                    logger.debug("SSDP receive error: %s", e)

                # Re-send M-SEARCH every 3 seconds
                now = asyncio.get_event_loop().time()
                if now - last_send >= 3.0:
                    try:
                        sock.sendto(SSDP_MSEARCH.encode(), (SSDP_ADDR, SSDP_PORT))
                        last_send = now
                    except OSError as e:
                        logger.debug("SSDP send error: %s", e)

                await asyncio.sleep(0.1)

            logger.info("Discovery complete. Found %s printers.", len(self._discovered))

        except OSError as e:
            if e.errno == 98:  # Address already in use
                logger.warning("Port %s is in use, trying alternative discovery...", SSDP_PORT)
                await self._discover_alternative(duration)
            else:
                logger.error("Discovery error: %s", e)
        except Exception as e:
            logger.error("Discovery error: %s", e)
        finally:
            self._running = False
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass  # Best-effort socket cleanup

    async def _discover_alternative(self, duration: float):
        """Alternative discovery using a random port (less reliable)."""
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
            sock.bind(("", 0))

            # Join multicast group
            mreq = struct.pack("4sl", socket.inet_aton(SSDP_ADDR), socket.INADDR_ANY)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

            logger.info("Using alternative discovery method...")

            start_time = asyncio.get_event_loop().time()
            last_send = start_time

            while self._running and (asyncio.get_event_loop().time() - start_time) < duration:
                try:
                    data, addr = sock.recvfrom(4096)
                    self._handle_response(data.decode("utf-8", errors="ignore"), addr[0])
                except BlockingIOError:
                    pass  # No data available yet on non-blocking socket
                except OSError as e:
                    logger.debug("SSDP receive error: %s", e)

                now = asyncio.get_event_loop().time()
                if now - last_send >= 2.0:
                    try:
                        sock.sendto(SSDP_MSEARCH.encode(), (SSDP_ADDR, SSDP_PORT))
                        last_send = now
                    except OSError:
                        pass  # Best-effort M-SEARCH resend; will retry next interval

                await asyncio.sleep(0.1)

            logger.info("Alternative discovery complete. Found %s printers.", len(self._discovered))
        except Exception as e:
            logger.error("Alternative discovery error: %s", e)
        finally:
            if sock:
                try:
                    sock.close()
                except OSError:
                    pass  # Best-effort socket cleanup

    def _handle_response(self, response: str, ip_address: str):
        """Parse SSDP response and extract printer info."""
        # Check if it's a Bambu Lab printer response
        if BAMBU_SEARCH_TARGET not in response and "bambulab" not in response.lower():
            logger.debug("Ignoring non-Bambu response from %s", ip_address)
            return

        # Extract USN (Unique Service Name) which contains the serial
        # Bambu format is just "USN: SERIALNUMBER" (no uuid: prefix)
        usn_match = re.search(r"USN:\s*(?:uuid:)?([^\s\r\n]+)", response, re.IGNORECASE)
        if not usn_match:
            logger.debug("No USN found in response from %s", ip_address)
            return

        serial = usn_match.group(1).strip()

        # Skip Bambuddy's own virtual printer (any model variant)
        if serial.endswith(VIRTUAL_PRINTER_SERIAL_SUFFIX):
            logger.debug("Ignoring Bambuddy virtual printer at %s", ip_address)
            return

        # Extract device name from LOCATION or DevName header
        name = serial  # Default to serial if no name found
        name_match = re.search(r"DevName\.bambu\.com:\s*(.+?)(?:\r\n|\n|$)", response, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()

        # Try to extract model from DevModel header
        model = None
        model_match = re.search(r"DevModel\.bambu\.com:\s*(.+?)(?:\r\n|\n|$)", response, re.IGNORECASE)
        if model_match:
            model = model_match.group(1).strip()

        # Also try NT header for model
        if not model:
            nt_match = re.search(r"NT:\s*urn:bambulab-com:device:([^:]+)", response, re.IGNORECASE)
            if nt_match:
                model = nt_match.group(1).strip()

        # Skip if already discovered
        if serial in self._discovered:
            return

        printer = DiscoveredPrinter(
            serial=serial,
            name=name,
            ip_address=ip_address,
            model=model,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )

        self._discovered[serial] = printer
        logger.info("Discovered printer: %s (%s) at %s", name, serial, ip_address)


class SubnetScanner:
    """Scanner for discovering Bambu printers by probing IP addresses."""

    # Bambu printer ports
    MQTT_PORT = 8883
    FTP_PORT = 990

    def __init__(self):
        self._discovered: dict[str, DiscoveredPrinter] = {}
        self._running = False
        self._scanned = 0
        self._total = 0
        self._scan_id = 0
        self._active_scan_id: int | None = None
        self._scan_task: asyncio.Task[object] | None = None

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def discovered_printers(self) -> list[DiscoveredPrinter]:
        return list(self._discovered.values())

    @property
    def progress(self) -> tuple[int, int]:
        """Return (scanned, total) counts."""
        return self._scanned, self._total

    def start_scan(self, subnets: Sequence[str], timeout: float = 1.0) -> int | None:
        """Reserve the single scanner and publish its progress before scheduling."""
        networks = [ipaddress.IPv4Network(validate_scan_subnet(subnet)) for subnet in subnets]
        if not networks:
            raise ValueError("at least one subnet is required")
        validate_scan_timeout(timeout)
        if self._running:
            return None

        self._scan_id += 1
        self._active_scan_id = self._scan_id
        self._running = True
        self._discovered.clear()
        self._scanned = 0
        self._total = sum(_host_count(network) for network in networks)
        self._scan_task = None
        return self._scan_id

    def attach_scan_task(self, scan_id: int, task: asyncio.Task[object]) -> None:
        """Attach the background task so ``stop`` can cancel active probes."""
        if self._active_scan_id == scan_id and self._running:
            self._scan_task = task
        else:
            task.cancel()

    async def scan_subnet(self, subnet: str, timeout: float = 1.0) -> list[DiscoveredPrinter]:
        """Scan one private CIDR without allocating an address list."""
        return await self.scan_subnets([subnet], timeout)

    async def scan_subnets(
        self,
        subnets: Sequence[str],
        timeout: float = 1.0,
        *,
        scan_id: int | None = None,
    ) -> list[DiscoveredPrinter]:
        """Scan configured CIDRs with bounded parallel probes and cancellation."""
        normalized = [validate_scan_subnet(subnet) for subnet in subnets]
        timeout = validate_scan_timeout(timeout)
        if scan_id is None:
            scan_id = self.start_scan(normalized, timeout)
            if scan_id is None:
                return []
            current_task = asyncio.current_task()
            if current_task is not None:
                self.attach_scan_task(scan_id, current_task)
        elif scan_id != self._active_scan_id or not self._running:
            return []

        networks = [ipaddress.IPv4Network(subnet) for subnet in normalized]
        pending: set[asyncio.Task[None]] = set()
        hosts = (host for network in networks for host in network.hosts())

        try:
            logger.info("Starting subnet scan of %s hosts across %s subnet(s)", self._total, len(networks))
            while self._is_active(scan_id):
                while len(pending) < MAX_CONCURRENT_PROBES and self._is_active(scan_id):
                    try:
                        host = next(hosts)
                    except StopIteration:
                        break
                    pending.add(asyncio.create_task(self._probe_host(str(host), timeout)))

                if not pending:
                    break

                completed, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
                for task in completed:
                    try:
                        task.result()
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        logger.debug("Subnet probe failed", exc_info=True)
                if self._is_active(scan_id):
                    self._scanned += len(completed)

            if self._is_active(scan_id):
                logger.info("Subnet scan complete. Found %s printers.", len(self._discovered))
            return self.discovered_printers
        finally:
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if self._active_scan_id == scan_id:
                self._running = False
                self._active_scan_id = None
                self._scan_task = None

    def _is_active(self, scan_id: int) -> bool:
        return self._running and self._active_scan_id == scan_id

    async def _probe_host(self, ip: str, timeout: float):
        """Probe a single host for Bambu printer ports."""
        # Check FTP port (990) - more reliable indicator
        ftp_open = await self._check_port(ip, self.FTP_PORT, timeout)
        if not ftp_open:
            return

        # Also check MQTT port (8883) for confirmation
        mqtt_open = await self._check_port(ip, self.MQTT_PORT, timeout)
        if not mqtt_open:
            return

        # Both ports open - likely a Bambu printer
        logger.info("Found potential Bambu printer at %s", ip)

        # Try to get printer info via SSDP unicast
        serial, name, model = await self._get_printer_info_ssdp(ip, timeout)

        # Skip Bambuddy's own virtual printer (any model variant)
        if serial and serial.endswith(VIRTUAL_PRINTER_SERIAL_SUFFIX):
            logger.debug("Ignoring Bambuddy virtual printer at %s", ip)
            return

        printer = DiscoveredPrinter(
            serial=serial or f"unknown-{ip.replace('.', '-')}",
            name=name or f"Printer at {ip}",
            ip_address=ip,
            model=model,
            discovered_at=datetime.now(timezone.utc).isoformat(),
        )
        self._discovered[ip] = printer

    async def _get_printer_info_ssdp(self, ip: str, timeout: float) -> tuple[str | None, str | None, str | None]:
        """Try to get printer info via SSDP unicast query."""
        loop = asyncio.get_event_loop()

        def _query():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                sock.settimeout(timeout)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

                # Send M-SEARCH directly to the printer
                msearch = (
                    "M-SEARCH * HTTP/1.1\r\n"
                    f"HOST: {ip}:{SSDP_PORT}\r\n"
                    'MAN: "ssdp:discover"\r\n'
                    "MX: 1\r\n"
                    f"ST: {BAMBU_SEARCH_TARGET}\r\n"
                    "\r\n"
                )
                sock.sendto(msearch.encode(), (ip, SSDP_PORT))

                # Wait for response
                data, _ = sock.recvfrom(4096)
                response = data.decode("utf-8", errors="ignore")
                sock.close()

                # Parse response
                serial = None
                name = None
                model = None

                usn_match = re.search(r"USN:\s*(?:uuid:)?([^\s\r\n]+)", response, re.IGNORECASE)
                if usn_match:
                    serial = usn_match.group(1).strip()

                name_match = re.search(r"DevName\.bambu\.com:\s*(.+?)(?:\r\n|\n|$)", response, re.IGNORECASE)
                if name_match:
                    name = name_match.group(1).strip()

                model_match = re.search(r"DevModel\.bambu\.com:\s*(.+?)(?:\r\n|\n|$)", response, re.IGNORECASE)
                if model_match:
                    model = model_match.group(1).strip()

                logger.debug("SSDP info from %s: serial=%s, name=%s, model=%s", ip, serial, name, model)
                return serial, name, model

            except OSError as e:
                logger.debug("SSDP query to %s failed: %s", ip, e)
                return None, None, None

        return await loop.run_in_executor(None, _query)

    async def _check_port(self, ip: str, port: int, timeout: float) -> bool:
        """Check if a port is open on the given IP."""
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
            writer.close()
            await writer.wait_closed()
            logger.debug("Port %s open on %s", port, ip)
            return True
        except TimeoutError:
            return False
        except ConnectionRefusedError:
            return False
        except OSError as e:
            # Log first few errors to help debug network issues
            if self._scanned < 5:
                logger.debug("OSError checking %s:%s: %s", ip, port, e)
            return False

    def stop(self) -> None:
        """Cancel the current scan and any in-flight bounded probe window."""
        task = self._scan_task
        self._running = False
        self._active_scan_id = None
        self._scan_task = None
        if task is not None and not task.done():
            task.cancel()


class TasmotaScanner:
    """Scanner for discovering Tasmota devices by probing IP addresses."""

    HTTP_PORT = 80

    def __init__(self):
        self._discovered: dict[str, dict] = {}
        self._running = False
        self._scanned = 0
        self._total = 0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def discovered_devices(self) -> list[dict]:
        return list(self._discovered.values())

    @property
    def progress(self) -> tuple[int, int]:
        """Return (scanned, total) counts."""
        return self._scanned, self._total

    async def scan_range(self, from_ip: str, to_ip: str, timeout: float = 1.0) -> list[dict]:
        """Scan an IP range for Tasmota devices.

        Args:
            from_ip: Starting IP address (e.g., "192.168.1.1")
            to_ip: Ending IP address (e.g., "192.168.1.254")
            timeout: Connection timeout per host in seconds

        Returns:
            List of discovered Tasmota devices
        """
        if self._running:
            return []

        self._running = True
        self._discovered.clear()
        self._scanned = 0

        try:
            start = ipaddress.ip_address(from_ip)
            end = ipaddress.ip_address(to_ip)

            # Generate list of IPs in range
            hosts = []
            current = start
            while current <= end:
                hosts.append(str(current))
                current = ipaddress.ip_address(int(current) + 1)

            self._total = len(hosts)

            if self._total > 1024:
                logger.warning("IP range has %s hosts, limiting to 1024", self._total)
                self._total = 1024
                hosts = hosts[:1024]

            logger.info("Starting Tasmota scan from %s to %s (%s hosts)", from_ip, to_ip, self._total)

            # Scan in batches to avoid overwhelming the network
            batch_size = 50
            for i in range(0, len(hosts), batch_size):
                if not self._running:
                    logger.info("Tasmota scan stopped by user")
                    break

                batch = hosts[i : i + batch_size]
                tasks = [self._probe_host(ip) for ip in batch]
                try:
                    await asyncio.gather(*tasks, return_exceptions=True)
                except Exception as e:
                    logger.warning("Batch %s error: %s", i // batch_size, e)
                self._scanned = min(i + batch_size, len(hosts))

            logger.info("Tasmota scan complete. Found %s devices.", len(self._discovered))
            return self.discovered_devices

        except ValueError as e:
            logger.error("Invalid IP address format: %s", e)
            return []
        finally:
            self._running = False

    async def _probe_host(self, ip: str):
        """Probe a single host for Tasmota HTTP API."""
        try:
            # Hard timeout of 5 seconds max per host
            await asyncio.wait_for(self._do_probe(ip), timeout=5.0)
        except TimeoutError:
            pass  # Host did not respond in time; skip
        except Exception:
            pass  # Probe failed for this host; skip silently

    async def _do_probe(self, ip: str):
        """Actually probe the host."""
        import httpx

        try:
            # Reasonable timeouts for network scanning
            client_timeout = httpx.Timeout(3.0, connect=1.0)
            async with httpx.AsyncClient(timeout=client_timeout, follow_redirects=False) as client:
                # First try simple Power command - most reliable indicator of Tasmota
                power_url = f"http://{ip}/cm?cmnd=Power"
                try:
                    power_response = await client.get(power_url)
                    if power_response.status_code == 401:
                        # Device requires auth - still a Tasmota device!
                        logger.info("Discovered Tasmota at %s (requires auth - 401)", ip)
                        device = {
                            "ip_address": ip,
                            "name": f"Tasmota ({ip})",
                            "module": None,
                            "state": "UNKNOWN",
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                        }
                        self._discovered[ip] = device
                        return

                    if power_response.status_code != 200:
                        return

                    power_data = power_response.json()

                    # Check for Tasmota auth warning (returns 200 with WARNING)
                    if "WARNING" in power_data:
                        logger.info("Discovered Tasmota at %s (requires auth)", ip)
                        device = {
                            "ip_address": ip,
                            "name": f"Tasmota ({ip})",
                            "module": None,
                            "state": "UNKNOWN",
                            "discovered_at": datetime.now(timezone.utc).isoformat(),
                        }
                        self._discovered[ip] = device
                        return

                    # Check if response looks like Tasmota (has POWER or POWER1 key)
                    power_state = power_data.get("POWER") or power_data.get("POWER1")
                    if power_state is None:
                        return

                except Exception as e:
                    logger.debug("Error probing %s: %s", ip, e)
                    return

                # It's a Tasmota device! Now get more info
                device_name = f"Tasmota ({ip})"
                module = None

                # Try to get device name from Status 0
                try:
                    status_url = f"http://{ip}/cm?cmnd=Status%200"
                    status_response = await client.get(status_url)
                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        if "Status" in status_data:
                            status = status_data["Status"]
                            device_name = status.get("DeviceName") or device_name
                            if not device_name or device_name == f"Tasmota ({ip})":
                                # Try FriendlyName
                                friendly = status.get("FriendlyName")
                                if friendly and isinstance(friendly, list) and friendly[0]:
                                    device_name = friendly[0]
                            module = status.get("Module")
                except Exception:
                    pass  # Status query is optional; proceed with defaults

                device = {
                    "ip_address": ip,
                    "name": device_name,
                    "module": module,
                    "state": power_state,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                }

                self._discovered[ip] = device
                logger.info("Discovered Tasmota device: %s at %s", device_name, ip)

        except httpx.TimeoutException:
            pass  # Host unreachable or too slow; not a Tasmota device
        except httpx.ConnectError:
            pass  # Connection refused; no HTTP server on this host
        except Exception:
            pass  # Unexpected error probing host; skip silently

    def stop(self):
        """Stop the current scan."""
        self._running = False


# Global instances
discovery_service = PrinterDiscoveryService()
subnet_scanner = SubnetScanner()
tasmota_scanner = TasmotaScanner()
