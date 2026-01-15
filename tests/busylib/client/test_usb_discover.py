import errno

from busylib.client import usb


class FakeNonBlockingSocket:
    """
    Fake socket for non-blocking discovery tests.
    """

    def __init__(self, connect_code: int, so_error: int) -> None:
        """
        Store connect and socket error codes for the probe.
        """
        self.connect_code = connect_code
        self.so_error = so_error
        self.blocking: bool | None = None
        self.closed = False
        self.connected_to: tuple[str, int] | None = None

    def setblocking(self, flag: bool) -> None:
        """
        Record the blocking mode.
        """
        self.blocking = flag

    def connect_ex(self, address: tuple[str, int]) -> int:
        """
        Record the connect address and return the configured code.
        """
        self.connected_to = address
        return self.connect_code

    def getsockopt(self, _level: int, _optname: int) -> int:
        """
        Return the configured SO_ERROR value.
        """
        return self.so_error

    def close(self) -> None:
        """
        Mark the socket as closed.
        """
        self.closed = True


def test_usb_discover_nonblocking_success(monkeypatch) -> None:
    """
    Ensure discover uses non-blocking connect and readiness checks.
    """
    fake_socket = FakeNonBlockingSocket(errno.EINPROGRESS, 0)
    calls: dict[str, object] = {}

    def fake_socket_factory(*_args, **_kwargs):
        return fake_socket

    def fake_select(_r, w, _x, timeout):
        calls["timeout"] = timeout
        return ([], w, [])

    monkeypatch.setattr(usb.socket, "socket", fake_socket_factory)
    monkeypatch.setattr(usb.select, "select", fake_select)

    controller = usb.UsbController(host="10.0.4.20", port=23, timeout=1.5)
    assert controller.discover() is True
    assert fake_socket.blocking is False
    assert fake_socket.connected_to == ("10.0.4.20", 23)
    assert fake_socket.closed is True
    assert calls["timeout"] == 1.5
