from __future__ import annotations

import pytest

from busylib import exceptions
from busylib.converter import convert_for_storage


def test_convert_for_storage_raises_domain_error_on_failure(monkeypatch) -> None:
    """
    Ensure converter errors are exposed as domain conversion failures.
    """

    def _boom(_path: str, _data: bytes) -> tuple[str, bytes] | None:
        """
        Simulate a failing converter for error-path coverage.
        """
        raise RuntimeError("boom")

    monkeypatch.setattr("busylib.converter.audio.convert", _boom)
    with pytest.raises(exceptions.BusyBarConversionError) as exc:
        convert_for_storage("sound.mp3", b"abc")
    assert exc.value.path == "sound.mp3"
    assert isinstance(exc.value.__cause__, RuntimeError)


def test_convert_for_storage_passthrough_unknown_ext() -> None:
    """
    Ensure unknown file types are returned unchanged.
    """
    path, payload = convert_for_storage("note.unknown", b"data")
    assert path == "note.unknown"
    assert payload == b"data"


def test_convert_for_storage_rejects_video_formats() -> None:
    """
    Ensure unsupported video formats raise a domain conversion error.
    """
    with pytest.raises(exceptions.BusyBarConversionError) as exc:
        convert_for_storage("clip.mp4", b"data")
    assert exc.value.path == "clip.mp4"
    assert isinstance(exc.value.__cause__, NotImplementedError)
