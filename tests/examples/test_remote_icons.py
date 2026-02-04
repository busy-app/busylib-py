from __future__ import annotations

import importlib


remote_main = importlib.import_module("examples.remote.main")


def test_select_icon_set_prefers_named_mode() -> None:
    """
    Ensure explicit mode selection returns the matching icon set.

    This protects the fallback logic from overriding valid modes.
    """
    icons = remote_main._select_icon_set("text")
    assert icons["pixel"] == remote_main.ICON_SETS["text"]["pixel"]
    assert icons["wifi"] == "WIFI"


def test_select_icon_set_falls_back_to_emoji() -> None:
    """
    Ensure unknown modes fall back to the emoji icon set.

    This keeps the UI stable when the constant is mistyped.
    """
    icons = remote_main._select_icon_set("unknown")
    assert icons == remote_main.ICON_SETS["emoji"]


def test_pixel_char_matches_selected_icons() -> None:
    """
    Ensure the default pixel character matches the selected icon set.

    This keeps CLI defaults consistent with the chosen mode.
    """
    assert remote_main.PIXEL_CHAR == remote_main.ICONS["pixel"]
