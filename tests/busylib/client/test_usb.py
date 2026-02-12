import socket

import pytest

from busylib import exceptions
from busylib.client import usb


class FakeTelnetSocket:
    """
    Fake socket for deterministic telnet exchange tests.

    Responses are keyed by sendall call index.
    """

    def __init__(self, responses_by_send: dict[int, list[bytes]]) -> None:
        """
        Initialize the fake socket with staged responses.

        Each sendall call increments the internal counter.
        """
        self.responses_by_send = {
            key: list(value) for key, value in responses_by_send.items()
        }
        self.sent: list[bytes] = []
        self._send_count = 0
        self._timeout: float | None = None
        self.closed = False

    def settimeout(self, value: float | None) -> None:
        """
        Store the timeout value passed by the client.

        The fake socket does not enforce timeouts.
        """
        self._timeout = value

    def sendall(self, data: bytes) -> None:
        """
        Record outgoing bytes and advance the send counter.

        The counter is used to stage responses.
        """
        self.sent.append(data)
        self._send_count += 1

    def recv(self, _size: int) -> bytes:
        """
        Return staged response data or raise a timeout when empty.

        The timeout exception signals idle reads to the client.
        """
        responses = self.responses_by_send.get(self._send_count, [])
        if responses:
            return responses.pop(0)
        raise socket.timeout()

    def close(self) -> None:
        """
        Mark the socket as closed.

        The fake socket does not release real resources.
        """
        self.closed = True


def test_send_command_telnet_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure telnet handshake, command send, and response cleaning work.

    The response should strip telnet control bytes, echo, and prompt lines.
    """
    monkeypatch.setattr(
        usb.UsbController,
        "find_device",
        lambda self: "10.0.4.20",
    )

    banner = b"\xff\xfb\x01BUSY BAR CLI\r\ncli> "
    response = (
        b"\xff\xfb\x01"
        b"device_info\r\n"
        b"name : BUSY Bar\r\n"
        b"u5_firmware_commit : 2635c44f\r\n"
        b"cli> "
    )
    fake_socket = FakeTelnetSocket({2: [banner], 3: [response]})

    def fake_create_connection(
        address: tuple[str, int],
        timeout: float,
    ) -> FakeTelnetSocket:
        assert address == ("10.0.4.20", 23)
        assert timeout == 2.0
        return fake_socket

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)

    controller = usb.UsbController(host="10.0.4.20", port=23, timeout=2.0)
    output = controller.send_command("device_info")

    assert output == "name : BUSY Bar\nu5_firmware_commit : 2635c44f"
    assert fake_socket.sent[0] == usb.UsbController._handshake_bytes
    assert fake_socket.sent[1] == b"\r\n"
    assert fake_socket.sent[2] == b"device_info\r\n"


def test_usb_controller_init_does_not_connect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure controller init does not attempt discovery.
    """

    def fail_discovery(self) -> str | None:
        raise AssertionError("find_device should not be called on init")

    monkeypatch.setattr(usb.UsbController, "find_device", fail_discovery)

    controller = usb.UsbController(host="10.0.4.20", port=23, timeout=2.0)

    assert controller.is_connected is False


@pytest.mark.asyncio
async def test_async_usb_send_command_runs_in_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure async USB commands are executed via asyncio.to_thread.
    """
    calls: dict[str, object] = {}

    async def fake_to_thread(func, *args, **kwargs):
        calls["func"] = func
        calls["args"] = args
        calls["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(usb.asyncio, "to_thread", fake_to_thread)

    controller = usb.AsyncUsbController(host="10.0.4.20", port=23)
    result = await controller.send_command("device_info")

    assert result == "ok"
    assert calls["func"] == controller._controller.send_command


@pytest.mark.asyncio
async def test_async_usb_discover_runs_in_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    Ensure async USB discovery is executed via asyncio.to_thread.
    """
    calls: dict[str, object] = {}

    async def fake_to_thread(func, *args, **kwargs):
        calls["func"] = func
        calls["args"] = args
        calls["kwargs"] = kwargs
        return True

    monkeypatch.setattr(usb.asyncio, "to_thread", fake_to_thread)

    controller = usb.AsyncUsbController(host="10.0.4.20", port=23)
    result = await controller.discover()

    assert result is True
    assert calls["func"] == controller._controller.discover


def test_usb_reboot_raise_on_error() -> None:
    """
    Re-raise USB errors from reboot when strict mode is enabled.
    """

    controller = usb.UsbController(host="10.0.4.20", port=23, timeout=2.0)

    def fail_power(_subcommand: str = "info") -> str:
        raise exceptions.BusyBarUsbError("boom")

    controller.power = fail_power  # type: ignore[method-assign]

    with pytest.raises(exceptions.BusyBarUsbError):
        controller.reboot(raise_on_error=True)
