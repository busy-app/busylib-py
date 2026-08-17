"""
Where the BUSY cloud lives, and where its API documentation is published.

These addresses move, so they are named once here rather than pasted into
docstrings and guides that then go stale. That has already cost a release:
the cloud host was renamed before launch and this client kept pointing at the
old name for months.
"""

from __future__ import annotations

CLOUD_HOST = "https://api.busy.app"

# Two separate surfaces share the host. The account API sits at the root and
# takes an account-scope token; the device API sits under /busybar and takes a
# bar-scope token. They are not interchangeable - a token for one is refused
# by the other.
ACCOUNT_API_DOCS_URL = f"{CLOUD_HOST}/docs"
DEVICE_API_DOCS_URL = f"{CLOUD_HOST}/busybar/docs"
DEVICE_API_SPEC_URL = f"{CLOUD_HOST}/busybar/openapi.yaml"


def device_docs_url(firmware_version: str | None = None) -> str:
    """
    Return the device API documentation, optionally for one firmware version.

    The cloud keeps the documentation of every published firmware, selected by
    version rather than by API version - `1.1.1`, not `25.0.0`. Passing the
    value from `status().firmware.version` gives the page describing the
    endpoints that particular bar actually serves.

    >>> device_docs_url()
    'https://api.busy.app/busybar/docs'
    >>> device_docs_url("1.0.2")
    'https://api.busy.app/busybar/docs?urls.primaryName=1.0.2'
    """
    if not firmware_version:
        return DEVICE_API_DOCS_URL
    return f"{DEVICE_API_DOCS_URL}?urls.primaryName={firmware_version}"


def device_spec_url(firmware_version: str | None = None) -> str:
    """
    Return the machine-readable OpenAPI document for a firmware version.

    This is the same content the documentation page renders, which makes it
    the way to ask what a given firmware supports without having that bar to
    hand.

    >>> device_spec_url("1.0.2")
    'https://api.busy.app/busybar/openapi.yaml?Name=1.0.2'
    """
    if not firmware_version:
        return DEVICE_API_SPEC_URL
    return f"{DEVICE_API_SPEC_URL}?Name={firmware_version}"
