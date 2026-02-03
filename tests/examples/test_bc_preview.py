from __future__ import annotations

from types import SimpleNamespace

from examples.bc.models import Entry
from examples.bc.panels import RemotePanel
from examples.bc.preview import PreviewMode, preview_remote


class _DummyClient:
    """
    Minimal client stub for preview tests.

    Records calls and returns fixed data where needed.
    """

    def __init__(self) -> None:
        """
        Initialize the stub with a call log.
        """
        self.calls: list[tuple[str, object]] = []

    def play_audio(self, app_id: str, path: str) -> None:
        """
        Record audio play requests.
        """
        self.calls.append(("play_audio", (app_id, path)))

    def read_storage_file(self, path: str) -> bytes:
        """
        Return a small text payload for previews.
        """
        self.calls.append(("read_storage_file", path))
        return b"line1\nline2"

    def draw_on_display(self, payload: object) -> None:
        """
        Record display draw requests.
        """
        self.calls.append(("draw_on_display", payload))


class _DummyRunner:
    """
    Runner stub that executes calls inline.
    """

    def __init__(self, client: _DummyClient) -> None:
        """
        Store the stub client for preview logic.
        """
        self.client = client

    def run(self, coro: object) -> object:
        """
        Return the provided object directly.
        """
        return coro

    def require_client(self) -> _DummyClient:
        """
        Return the attached client.
        """
        return self.client


def _make_remote_panel(entry: Entry, client: _DummyClient) -> RemotePanel:
    """
    Build a RemotePanel without invoking network refresh.
    """
    panel = RemotePanel.__new__(RemotePanel)
    panel.runner = _DummyRunner(client)
    panel.cwd = "/ext/assets/app"
    panel.error = None
    panel.entries = [entry]
    panel.index = 0
    return panel


def test_preview_remote_audio_mode() -> None:
    """
    Ensure WAV previews return audio mode.
    """
    entry = Entry(name="sound.wav", is_dir=False, size=0)
    client = _DummyClient()
    panel = _make_remote_panel(entry, client)
    status: list[str] = []

    mode = preview_remote(panel, status, panel.runner)

    assert mode is PreviewMode.AUDIO
    assert any("Playing" in message for message in status)


def test_preview_remote_static_mode() -> None:
    """
    Ensure image previews return static mode.
    """
    entry = Entry(name="cover.png", is_dir=False, size=0)
    client = _DummyClient()
    panel = _make_remote_panel(entry, client)
    status: list[str] = []

    mode = preview_remote(panel, status, panel.runner)

    assert mode is PreviewMode.STATIC


def test_preview_remote_thread_mode(monkeypatch) -> None:
    """
    Ensure text previews return threaded mode.
    """
    entry = Entry(name="readme.txt", is_dir=False, size=0)
    client = _DummyClient()
    panel = _make_remote_panel(entry, client)
    status: list[str] = []
    called = SimpleNamespace(seen=False)

    def _fake_start(
        app_id: str,
        rel_path: str,
        client_arg: _DummyClient,
        runner: _DummyRunner,
        lines: list[str],
    ) -> None:
        """
        Record that text preview threading was requested.
        """
        called.seen = True

    monkeypatch.setattr(
        "examples.bc.preview.start_text_preview_thread",
        _fake_start,
    )

    mode = preview_remote(panel, status, panel.runner)

    assert mode is PreviewMode.THREAD
    assert called.seen is True
