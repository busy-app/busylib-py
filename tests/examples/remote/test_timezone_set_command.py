from __future__ import annotations

from examples.remote.commands.timezone_set import resolve_timezone


def test_resolve_timezone_offset() -> None:
    """
    Resolve a numeric offset into an Etc/GMT timezone.
    """
    timezone, error = resolve_timezone(
        "+3",
        {"Etc/GMT-3", "Etc/UTC"},
    )

    assert timezone == "Etc/GMT-3"
    assert error is None


def test_resolve_timezone_city_name() -> None:
    """
    Resolve a city name to a unique IANA timezone.
    """
    timezone, error = resolve_timezone("Moscow", {"Europe/Moscow"})

    assert timezone == "Europe/Moscow"
    assert error is None


def test_resolve_timezone_ambiguous_city() -> None:
    """
    Return an error when a city name maps to multiple zones.
    """
    timezone, error = resolve_timezone(
        "Springfield",
        {"America/Springfield", "Etc/Springfield"},
    )

    assert timezone is None
    assert error is not None
    assert "ambiguous" in error
