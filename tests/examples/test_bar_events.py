from __future__ import annotations

from examples.bar_events.main import _format_event


def test_format_event_parses_json_text() -> None:
    """
    Ensure JSON text messages are normalized for stable output.

    The formatter should emit sorted JSON keys to simplify log comparisons.
    """
    result = _format_event('{"state":"press","key":"ok"}')

    assert result == 'json {"key": "ok", "state": "press"}'


def test_format_event_keeps_plain_text() -> None:
    """
    Ensure non-JSON text messages are preserved as plain text.

    This keeps unexpected server notices visible without parsing failures.
    """
    result = _format_event("hello")

    assert result == "text hello"


def test_format_event_renders_binary_payload() -> None:
    """
    Ensure binary websocket messages include length and hex dump.

    Binary visibility is useful when input stream sends compact wire payloads.
    """
    result = _format_event(b"\x01\x0a")

    assert result == "binary len=2 hex=010a"
