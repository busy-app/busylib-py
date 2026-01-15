from __future__ import annotations

import pytest

from busylib.converter import convert_for_storage


def test_convert_for_storage_fallback_on_error(monkeypatch) -> None:
    """
    Ensure converter errors fall back to original path and data.
    """

    def _boom(_path: str, _data: bytes) -> tuple[str, bytes] | None:
        """
        Simulate a failing converter for error-path coverage.
        """
        raise RuntimeError("boom")

    monkeypatch.setattr("busylib.converter.audio.convert", _boom)
    path, payload = convert_for_storage("sound.mp3", b"abc")
    assert path == "sound.mp3"
    assert payload == b"abc"


def test_convert_for_storage_passthrough_unknown_ext() -> None:
    """
    Ensure unknown file types are returned unchanged.
    """
    path, payload = convert_for_storage("note.unknown", b"data")
    assert path == "note.unknown"
    assert payload == b"data"


def test_convert_for_storage_rejects_video_formats() -> None:
    """
    Ensure video formats raise NotImplementedError to block copy.
    """
    with pytest.raises(NotImplementedError, match="Video/animation conversion"):
        convert_for_storage("clip.mp4", b"data")
