import pytest

from busylib import display, types
from busylib.features import DeviceSnapshot
from examples.remote import constants, renderers


def test_strip_ansi_removes_sequences() -> None:
    """
    Ensure ANSI escape codes are removed for layout calculations.
    """
    text = "\x1b[1mBold\x1b[0m text"
    assert renderers.TerminalRenderer._strip_ansi(text) == "Bold text"


def test_renderer_handles_resize_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure renderer falls back when terminal size lookup fails.
    """

    def broken_terminal_size(*_args, **_kwargs):
        """
        Simulate a terminal resize error.
        """
        raise OSError("boom")

    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer=" ",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(renderers.shutil, "get_terminal_size", broken_terminal_size)

    frame = bytes(display.FRONT_DISPLAY.width * display.FRONT_DISPLAY.height * 3)
    renderer.render(frame)


def test_renderer_shows_link_status() -> None:
    """
    Ensure link status shows the correct icon and optional key.
    """
    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer=" ",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    snapshot = DeviceSnapshot(name="BusyBar")
    renderer.update_info(snapshot=snapshot, link_connected=True)
    line = renderer._format_info_line()
    assert "LINK" in line

    renderer.update_info(link_connected=False, link_key="ABCD")
    line = renderer._format_info_line()
    assert "NOLINK ABCD" in line

    renderer.update_info(link_connected=True, link_email="name@example.com")
    line = renderer._format_info_line()
    assert "LINK name@example.com" in line


def test_renderer_shows_update_available() -> None:
    """
    Ensure update availability icon is rendered near version.
    """
    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer=" ",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    snapshot = DeviceSnapshot(name="BusyBar")
    snapshot.system = types.StatusSystem(version="1.2.3")
    renderer.update_info(snapshot=snapshot, update_available=True)
    line = renderer._format_info_line()
    assert "SYS 1.2.3 UPDATE" in line


def test_renderer_shows_wifi_ip_and_signal() -> None:
    """
    Ensure Wi-Fi info shows IP address and RSSI-based icon.
    """
    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer=" ",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    wifi = types.StatusResponse(
        ssid="TestNet",
        rssi=-50,
        ip_config=types.WifiIpConfig(address="192.168.1.10"),
    )
    snapshot = DeviceSnapshot(name="BusyBar")
    snapshot.wifi = wifi
    renderer.update_info(snapshot=snapshot)
    line = renderer._format_info_line()
    assert "WIFI3 TestNet 192.168.1.10" in line


def test_renderer_shows_link_without_snapshot() -> None:
    """
    Ensure link status renders even without a snapshot.
    """
    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer=" ",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    renderer.update_info(link_connected=True)
    line = renderer._format_info_line()
    assert "LINK" in line


def test_renderer_command_line_initializes() -> None:
    """
    Ensure command line state is initialized before size calculations.
    """
    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer=" ",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    renderer.update_command_line("help", cursor=4)
    renderer._update_size(force=True)


def test_renderer_hides_command_line_and_refreshes() -> None:
    """
    Ensure command line hides after clearing and keeps last frame.
    """
    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer=" ",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    frame = bytes(display.FRONT_DISPLAY.width * display.FRONT_DISPLAY.height * 3)
    renderer.render(frame)
    renderer.update_command_line("hi", cursor=2)
    renderer.update_command_line(None)
    assert renderer._command_line is None


def test_renderer_applies_full_frame() -> None:
    """
    Ensure frame is applied around rendered lines.
    """
    old_char = renderers.settings.frame_char
    renderers.settings.frame_char = "#"
    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer=" ",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        frame_mode="full",
        clear_screen=lambda *_args, **_kwargs: None,
    )
    framed = renderer._apply_frame(["abcd"])
    renderers.settings.frame_char = old_char
    assert len(framed) == 3
    assert renderers.TerminalRenderer._strip_ansi(framed[0]).startswith("#")
    assert renderers.TerminalRenderer._strip_ansi(framed[1]).startswith("#")
    assert renderers.TerminalRenderer._strip_ansi(framed[2]).endswith("#")


def test_full_frame_adds_right_padding_space() -> None:
    """
    Ensure full frame inserts a gap before the right border.
    """
    renderer = renderers.TerminalRenderer(
        spec=display.FRONT_DISPLAY,
        spacer="",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        frame_mode="full",
        clear_screen=lambda *_args, **_kwargs: None,
    )
    framed = renderer._apply_frame(["abcd"])
    frame_char = renderers.settings.frame_char[:1] or "-"
    assert f"abcd {frame_char}" in renderers.TerminalRenderer._strip_ansi(framed[1])


def test_renderer_black_pixel_opacity_settings(capsys) -> None:
    """
    Ensure black pixels render as opaque unless transparency is enabled.
    """
    spec = display.DisplaySpec(
        name=display.DisplayName.FRONT,
        index=0,
        width=1,
        height=1,
        description="test",
    )
    renderer = renderers.TerminalRenderer(
        spec=spec,
        spacer="",
        pixel_char="*",
        icons=constants.ICON_SETS["text"],
        clear_screen=lambda *_args, **_kwargs: None,
    )
    frame = bytes([0, 0, 0])

    old_setting = renderers.settings.black_pixels_transparent
    try:
        renderers.settings.black_pixels_transparent = False
        renderer.render(frame)
        output = capsys.readouterr().out
        assert "\x1b[38;2;0;0;0m*\x1b[0m" in output

        renderers.settings.black_pixels_transparent = True
        renderer.render(frame)
        output = capsys.readouterr().out
        assert " " in output
        assert "\x1b[38;2;0;0;0m*\x1b[0m" not in output
    finally:
        renderers.settings.black_pixels_transparent = old_setting
