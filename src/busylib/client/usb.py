import asyncio
import errno
import logging
import select
import socket
import time
from collections.abc import Callable
from typing import ParamSpec, TypeVar

from .. import exceptions

logger = logging.getLogger(__name__)


P = ParamSpec("P")
R = TypeVar("R")


def _strip_telnet_commands(payload: bytes) -> bytes:
    """
    Remove telnet IAC sequences from a byte payload.

    This keeps literal 0xFF bytes when escaped as IAC IAC and drops
    negotiation triplets like IAC WILL/WONT/DO/DONT.
    """
    result = bytearray()
    idx = 0
    while idx < len(payload):
        byte = payload[idx]
        if byte != 0xFF:
            result.append(byte)
            idx += 1
            continue

        if idx + 1 >= len(payload):
            break

        command = payload[idx + 1]
        if command == 0xFF:
            result.append(0xFF)
            idx += 2
            continue

        if idx + 2 >= len(payload):
            break

        idx += 3

    return bytes(result)


def _read_until_idle(
    sock: socket.socket,
    idle_timeout: float,
    *,
    chunk_size: int = 4096,
) -> bytes:
    """
    Read from the socket until no new data arrives for idle_timeout seconds.

    The timeout resets after each successful read so short bursts are captured
    as a single response.
    """
    chunks: list[bytes] = []
    deadline = time.monotonic() + idle_timeout

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        sock.settimeout(remaining)
        try:
            data = sock.recv(chunk_size)
        except socket.timeout:
            break

        if not data:
            break

        chunks.append(data)
        deadline = time.monotonic() + idle_timeout

    return b"".join(chunks)


def _is_prompt_line(line: str) -> bool:
    """
    Decide whether a line looks like a CLI prompt.

    Prompts are typically short lines ending with ">" without key/value pairs.
    """
    stripped = line.strip()
    if not stripped:
        return False
    if ":" in stripped:
        return False
    return stripped.endswith(">") and len(stripped) <= 32


def _clean_response(text: str, sent_cmd: str) -> str:
    """
    Remove echoed command and prompt lines from a CLI response.

    Keeps meaningful output lines and preserves original ordering.
    """
    lines = (line.strip() for line in text.replace("\r", "").split("\n"))
    cleaned: list[str] = []
    for line in lines:
        if not line:
            continue
        if line == sent_cmd:
            continue
        if _is_prompt_line(line):
            continue
        cleaned.append(line)

    return "\n".join(cleaned).strip()


class UsbController:
    """
    Controller for the Busy Bar CLI over telnet.

    The device exposes a CLI on 10.0.4.20:23 that mirrors USB commands.
    """

    _handshake_bytes = b"\xff\xfb\x01"

    def __init__(
        self,
        host: str | None = None,
        port: int = 23,
        *,
        timeout: float = 2.0,
        banner_timeout: float = 1.0,
        idle_timeout: float = 0.3,
    ) -> None:
        """
        Initialize the telnet controller without opening a connection.

        The host may include a ":port" suffix to override the port.
        """
        resolved_host = host or "10.0.4.20"
        resolved_port = port
        if resolved_host and ":" in resolved_host:
            host_part, port_part = resolved_host.rsplit(":", 1)
            if port_part.isdigit():
                resolved_host = host_part
                resolved_port = int(port_part)

        self._host = resolved_host
        self._port = resolved_port
        self._timeout = timeout
        self._banner_timeout = banner_timeout
        self._idle_timeout = idle_timeout
        self._connected_host: str | None = None

        logger.info("USB controller initialized for %s:%s", self._host, self._port)

    @property
    def is_connected(self) -> bool:
        """
        Report whether the last connectivity probe succeeded.

        This does not keep a persistent socket open.
        """
        return self._connected_host is not None

    def refresh_connection(self) -> bool:
        """
        Re-check telnet reachability and update the cached status.

        Returns True when the host is reachable, otherwise False.
        """
        self._connected_host = self.find_device()
        if self._connected_host:
            logger.debug("Telnet device found on %s:%s", self._host, self._port)
        else:
            logger.debug("Telnet device not found")
        return self.is_connected

    def find_device(self) -> str | None:
        """
        Attempt to connect to the configured host/port.

        Returns the host string on success or None on failure.
        """
        try:
            sock = socket.create_connection((self._host, self._port), self._timeout)
        except OSError as exc:
            logger.warning(
                "Configured telnet host %s:%s not accessible: %s",
                self._host,
                self._port,
                exc,
            )
            return None

        try:
            return self._host
        finally:
            sock.close()

    def discover(self) -> bool:
        """
        Probe whether the device is reachable without storing state.

        Returns True when a connection can be established.
        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setblocking(False)
            result = sock.connect_ex((self._host, self._port))
            if result == 0:
                return True
            if result not in {
                errno.EINPROGRESS,
                errno.EALREADY,
                errno.EWOULDBLOCK,
            }:
                return False
            _, writable, _ = select.select([], [sock], [], self._timeout)
            if not writable:
                return False
            return sock.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR) == 0
        finally:
            sock.close()

    def send_command(
        self,
        cmd: str,
        *args: str,
        timeout: float | None = None,
    ) -> str:
        """
        Send a CLI command over telnet and return the response text.

        Raises BusyBarUsbError when the device cannot be reached.
        """
        if not self.is_connected:
            if not self.refresh_connection():
                raise exceptions.BusyBarUsbError("USB device is not connected")

        full_cmd = f"{cmd} {' '.join(args)}".strip()
        effective_timeout = self._timeout if timeout is None else timeout

        try:
            response = self._send_telnet_command(full_cmd, effective_timeout)
        except Exception as exc:
            logger.error("Command '%s' failed: %s", full_cmd, exc)
            raise exceptions.BusyBarUsbError(f"Command failed: {exc}") from exc

        return response

    def _send_telnet_command(
        self,
        full_cmd: str,
        timeout: float,
    ) -> str:
        """
        Open a telnet session, exchange the command, and clean the response.

        This performs a lightweight handshake, reads the banner, and sends the
        CLI command terminated by CRLF.
        """
        sock = socket.create_connection((self._host, self._port), timeout)
        try:
            sock.settimeout(timeout)
            sock.sendall(self._handshake_bytes)
            sock.sendall(b"\r\n")
            _read_until_idle(sock, self._banner_timeout)

            sock.sendall(f"{full_cmd}\r\n".encode("utf-8"))
            raw = _read_until_idle(sock, self._idle_timeout)

            cleaned = _strip_telnet_commands(raw).decode("utf-8", errors="replace")
            return _clean_response(cleaned, full_cmd)
        finally:
            sock.close()

    def uptime(self) -> str:
        """
        Get device uptime via the CLI.

        Returns the raw CLI output.
        """
        return self.send_command("uptime")

    def power(self, subcommand: str = "info") -> str:
        """
        Run a power management subcommand.

        Use reboot/off/info/boot as subcommands.
        """
        return self.send_command("power", subcommand)

    def reboot(self, *, raise_on_error: bool = False) -> bool:
        """
        Reboot the device using the power command.

        Returns True on success and False on failure by default.
        If raise_on_error is True, re-raises BusyBarUsbError instead.
        """
        try:
            self.power("reboot")
            return True
        except exceptions.BusyBarUsbError:
            if raise_on_error:
                raise
            return False

    def storage(self, *args: str) -> str:
        """
        Execute file system commands in the storage namespace.

        Pass through arguments to the CLI.
        """
        return self.send_command("storage", *args)

    def update(self, *args: str) -> str:
        """
        Execute firmware update commands.

        Pass through arguments to the CLI.
        """
        return self.send_command("update", *args)

    def input(self, *args: str) -> str:
        """
        Execute input emulation commands.

        Pass through arguments to the CLI.
        """
        return self.send_command("input", *args)

    def loader(self, *args: str) -> str:
        """
        Execute application loader commands.

        Pass through arguments to the CLI.
        """
        return self.send_command("loader", *args)

    def top(self) -> str:
        """
        Retrieve the process list and CPU usage snapshot.

        Returns the raw CLI output.
        """
        return self.send_command("top")

    def free(self) -> str:
        """
        Retrieve free memory summary.

        Returns the raw CLI output.
        """
        return self.send_command("free")

    def free_blocks(self) -> str:
        """
        Retrieve detailed memory block information.

        Returns the raw CLI output.
        """
        return self.send_command("free_blocks")

    def log(self) -> str:
        """
        Retrieve system log output.

        Returns the raw CLI output.
        """
        return self.send_command("log")

    def echo(self, message: str = "ping") -> str:
        """
        Send an echo message to the CLI.

        Returns the echoed response.
        """
        return self.send_command("echo", message)

    def device_info(self) -> str:
        """
        Retrieve device information such as firmware versions and MACs.

        Returns the raw CLI output.
        """
        return self.send_command("device_info")

    def date(self, *args: str) -> str:
        """
        Execute RTC commands.

        Pass through arguments to the CLI.
        """
        return self.send_command("date", *args)

    def wifi(self, *args: str) -> str:
        """
        Execute WiFi stack debugging commands.

        Pass through arguments to the CLI.
        """
        return self.send_command("wifi", *args)

    def ble(self, *args: str) -> str:
        """
        Execute BLE stack debugging commands.

        Pass through arguments to the CLI.
        """
        return self.send_command("ble", *args)

    def matter(self, *args: str) -> str:
        """
        Execute Matter protocol commands.

        Pass through arguments to the CLI.
        """
        return self.send_command("matter", *args)

    def crypto(self, *args: str) -> str:
        """
        Execute cryptographic test commands.

        Pass through arguments to the CLI.
        """
        return self.send_command("crypto", *args)


class AsyncUsbController:
    """
    Async wrapper for UsbController with thread-backed operations.

    All commands run in a worker thread to avoid blocking the event loop.
    """

    def __init__(
        self,
        host: str | None = None,
        port: int = 23,
        *,
        timeout: float = 2.0,
        banner_timeout: float = 1.0,
        idle_timeout: float = 0.3,
    ) -> None:
        """
        Initialize the async wrapper with a synchronous controller.
        """
        self._controller = UsbController(
            host=host,
            port=port,
            timeout=timeout,
            banner_timeout=banner_timeout,
            idle_timeout=idle_timeout,
        )

    @property
    def is_connected(self) -> bool:
        """
        Report whether the last discovery check succeeded.
        """
        return self._controller.is_connected

    async def _call(self, func: Callable[P, R], *args: P.args, **kwargs: P.kwargs) -> R:
        """
        Run a controller method in a background thread.
        """
        return await asyncio.to_thread(func, *args, **kwargs)

    async def refresh_connection(self) -> bool:
        """
        Re-check telnet reachability and update cached status.
        """
        return await self._call(self._controller.refresh_connection)

    async def discover(self) -> bool:
        """
        Probe whether the device is reachable without storing state.
        """
        return await self._call(self._controller.discover)

    async def send_command(
        self,
        cmd: str,
        *args: str,
        timeout: float | None = None,
    ) -> str:
        """
        Send a CLI command over telnet and return the response text.
        """
        return await self._call(
            self._controller.send_command, cmd, *args, timeout=timeout
        )

    async def uptime(self) -> str:
        """
        Get device uptime via the CLI.
        """
        return await self._call(self._controller.uptime)

    async def power(self, subcommand: str = "info") -> str:
        """
        Run a power management subcommand.
        """
        return await self._call(self._controller.power, subcommand)

    async def reboot(self, *, raise_on_error: bool = False) -> bool:
        """
        Reboot the device using the power command.
        """
        return await self._call(self._controller.reboot, raise_on_error=raise_on_error)

    async def storage(self, *args: str) -> str:
        """
        Execute file system commands in the storage namespace.
        """
        return await self._call(self._controller.storage, *args)

    async def update(self, *args: str) -> str:
        """
        Execute firmware update commands.
        """
        return await self._call(self._controller.update, *args)

    async def input(self, *args: str) -> str:
        """
        Execute input emulation commands.
        """
        return await self._call(self._controller.input, *args)

    async def loader(self, *args: str) -> str:
        """
        Execute application loader commands.
        """
        return await self._call(self._controller.loader, *args)

    async def top(self) -> str:
        """
        Retrieve the process list and CPU usage snapshot.
        """
        return await self._call(self._controller.top)

    async def free(self) -> str:
        """
        Retrieve free memory summary.
        """
        return await self._call(self._controller.free)

    async def free_blocks(self) -> str:
        """
        Retrieve detailed memory block information.
        """
        return await self._call(self._controller.free_blocks)

    async def log(self) -> str:
        """
        Retrieve system log output.
        """
        return await self._call(self._controller.log)

    async def echo(self, message: str = "ping") -> str:
        """
        Send an echo message to the CLI.
        """
        return await self._call(self._controller.echo, message)

    async def device_info(self) -> str:
        """
        Retrieve device information such as firmware versions and MACs.
        """
        return await self._call(self._controller.device_info)

    async def date(self, *args: str) -> str:
        """
        Execute RTC commands.
        """
        return await self._call(self._controller.date, *args)

    async def wifi(self, *args: str) -> str:
        """
        Execute WiFi stack debugging commands.
        """
        return await self._call(self._controller.wifi, *args)

    async def ble(self, *args: str) -> str:
        """
        Execute BLE stack debugging commands.
        """
        return await self._call(self._controller.ble, *args)

    async def matter(self, *args: str) -> str:
        """
        Execute Matter protocol commands.
        """
        return await self._call(self._controller.matter, *args)

    async def crypto(self, *args: str) -> str:
        """
        Execute cryptographic test commands.
        """
        return await self._call(self._controller.crypto, *args)
