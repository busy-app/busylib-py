from __future__ import annotations

from examples.remote.constants import ICON_SETS
from examples.remote.renderers import TerminalRenderer
from busylib import display


def _build_renderer() -> TerminalRenderer:
    """
    Build a renderer with deterministic terminal sizing.

    This keeps the output stable for tests.
    """
    spec = display.get_display_spec(display.FRONT_DISPLAY)
    renderer = TerminalRenderer(
        spec,
        spacer="",
        pixel_char="#",
        icons=ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    renderer._get_terminal_size = lambda: (60, 20)  # type: ignore[method-assign]
    return renderer


def test_status_line_renders_without_command_line(capsys) -> None:
    """
    Render a status line when no command line is active.

    The status text should appear in the output.
    """
    renderer = _build_renderer()
    renderer.update_status_line("timezone_set: ok Europe/Moscow")
    spec = renderer.spec
    renderer.render(bytes(spec.width * spec.height * 3))

    output = capsys.readouterr().out
    assert "status: timezone_set: ok Europe/Moscow" in output


def test_status_line_hidden_when_command_line_active(capsys) -> None:
    """
    Avoid rendering the status line when the command prompt is visible.

    The prompt should take precedence in the footer.
    """
    renderer = _build_renderer()
    renderer.update_status_line("timezone_set: ok Europe/Moscow")
    renderer.update_command_line("tz +3", cursor=3)
    spec = renderer.spec
    renderer.render(bytes(spec.width * spec.height * 3))

    output = capsys.readouterr().out
    plain_output = TerminalRenderer._strip_ansi(output)
    assert "status: timezone_set: ok Europe/Moscow" not in output
    assert ":tz +3" in plain_output
