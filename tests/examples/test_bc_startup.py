from busylib.exceptions import BusyBarAPIError
from examples.bc.startup import ensure_app_directory


class _DummyClient:
    """
    Minimal client stub for app directory checks.
    """

    def __init__(self, *, missing: bool) -> None:
        """
        Configure whether the directory should be missing.
        """
        self.missing = missing
        self.calls: list[tuple[str, str]] = []

    def list_storage_files(self, path: str) -> str:
        """
        Return path or raise BusyBarAPIError for missing directory.
        """
        self.calls.append(("list", path))
        if self.missing:
            raise BusyBarAPIError("HTTP 404: not found", code=404)
        return path

    def create_storage_directory(self, path: str) -> str:
        """
        Record directory creation calls.
        """
        self.calls.append(("mkdir", path))
        return path


class _DummyRunner:
    """
    Runner stub that returns values directly.
    """

    def __init__(self, client: _DummyClient) -> None:
        """
        Attach the dummy client.
        """
        self.client = client

    def run(self, coro: object) -> object:
        """
        Return coroutine values directly.
        """
        return coro

    def require_client(self) -> _DummyClient:
        """
        Return the attached client.
        """
        return self.client


def test_ensure_app_directory_creates_on_missing() -> None:
    """
    Ensure missing app directory is created on 404.
    """
    client = _DummyClient(missing=True)
    runner = _DummyRunner(client)

    path = ensure_app_directory(runner, "bc")

    assert path == "/ext/assets/bc"
    assert ("mkdir", "/ext/assets/bc") in client.calls


def test_ensure_app_directory_noop_when_exists() -> None:
    """
    Ensure existing app directory does not trigger mkdir.
    """
    client = _DummyClient(missing=False)
    runner = _DummyRunner(client)

    path = ensure_app_directory(runner, "bc")

    assert path == "/ext/assets/bc"
    assert all(call[0] != "mkdir" for call in client.calls)
