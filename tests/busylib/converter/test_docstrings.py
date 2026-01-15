from __future__ import annotations

import inspect

from busylib.converter import _registry, audio, convert_for_storage, image, video


def _doc_is_multiline(obj: object) -> bool:
    """
    Check that a docstring exists and spans multiple lines.

    This enforces documentation requirements for converter helpers.
    """
    doc = inspect.getdoc(obj)
    return doc is not None and "\n" in doc


def test_converter_docstrings_are_multiline() -> None:
    """
    Ensure converter functions explain their intent in multiline docstrings.

    Keeps documentation consistent across the conversion pipeline.
    """
    targets = [
        audio.convert,
        image._center_crop,
        image._resize_for_display,
        image.convert,
        video.convert,
        _registry,
        convert_for_storage,
    ]
    assert all(_doc_is_multiline(target) for target in targets)
