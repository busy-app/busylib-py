from __future__ import annotations

import pytest

from busylib import cloud


def test_the_two_surfaces_do_not_overlap() -> None:
    """
    Account and device documentation are separate addresses.

    They share a host but take different tokens, so conflating them sends
    people to a page that cannot describe what their token opens.
    """
    assert cloud.ACCOUNT_API_DOCS_URL == "https://api.busy.app/docs"
    assert cloud.DEVICE_API_DOCS_URL == "https://api.busy.app/busybar/docs"
    assert cloud.ACCOUNT_API_DOCS_URL != cloud.DEVICE_API_DOCS_URL


@pytest.mark.parametrize(
    "version,expected",
    [
        (None, "https://api.busy.app/busybar/docs"),
        ("", "https://api.busy.app/busybar/docs"),
        ("1.1.1", "https://api.busy.app/busybar/docs?urls.primaryName=1.1.1"),
        ("1.0.2", "https://api.busy.app/busybar/docs?urls.primaryName=1.0.2"),
        ("0.10.2-rc", "https://api.busy.app/busybar/docs?urls.primaryName=0.10.2-rc"),
    ],
)
def test_device_docs_url(version: str | None, expected: str) -> None:
    """
    Documentation is selected by firmware version, not by API version.
    """
    assert cloud.device_docs_url(version) == expected


@pytest.mark.parametrize(
    "version,expected",
    [
        (None, "https://api.busy.app/busybar/openapi.yaml"),
        ("1.1.1", "https://api.busy.app/busybar/openapi.yaml?Name=1.1.1"),
    ],
)
def test_device_spec_url(version: str | None, expected: str) -> None:
    """
    The spec uses its own parameter name, which is easy to get wrong.
    """
    assert cloud.device_spec_url(version) == expected


def test_the_client_default_matches_the_published_host() -> None:
    """
    The cloud default and the documented host cannot drift apart.
    """
    from busylib.settings import Settings

    assert Settings().cloud_base_url == cloud.CLOUD_HOST
