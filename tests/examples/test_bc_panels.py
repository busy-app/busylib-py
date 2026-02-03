from types import SimpleNamespace

from busylib.exceptions import BusyBarAPIError
from examples.bc.panels import RemotePanel


class _DummyClient:
    """
    Minimal client stub for remote panel tests.
    """

    def list_storage_files(self, path: str) -> str:
        """
        Return the path as a sentinel for the runner.
        """
        return path


class _DummyRunner:
    """
    Runner stub with path-aware behavior.
    """

    def __init__(self) -> None:
        """
        Initialize the runner and attach a dummy client.
        """
        self.client = _DummyClient()

    def run(self, coro: object) -> object:
        """
        Raise a 400 error on bad paths and return empty listing otherwise.
        """
        if coro == "/bad":
            raise BusyBarAPIError("HTTP 400: bad path", code=400)
        return SimpleNamespace(list=[])

    def require_client(self) -> _DummyClient:
        """
        Return the attached client.
        """
        return self.client


def test_remote_panel_resets_to_ext_on_400() -> None:
    """
    Ensure a 400 error resets the remote cwd to /ext.
    """
    panel = RemotePanel.__new__(RemotePanel)
    panel.runner = _DummyRunner()
    panel.cwd = "/bad"
    panel.error = None
    panel.entries = []
    panel.index = 0

    panel.refresh()

    assert panel.cwd == "/ext"
    assert panel.entries[0].name == ".."
    assert panel.error is not None
    assert "Reset to /ext" in panel.error
