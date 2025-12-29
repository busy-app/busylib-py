from __future__ import annotations

import os
import re

from . import exceptions


API_VERSION = os.environ.get("BUSY_API_VERSION", "0.1.0")
API_VERSION_HEADER = "X-Busy-Api-Version"


def _parse_major_minor(version: str) -> tuple[int, int]:
    """
    Extract major and minor numbers from semver-like strings.
    """
    match = re.match(r"^(\d+)\.(\d+)", version.strip())
    if not match:
        raise ValueError(f"Invalid API version format: {version}")
    return int(match.group(1)), int(match.group(2))


def ensure_compatible(*, library_version: str, device_version: str) -> None:
    """
    Validate device API version against the library support matrix.
    """
    lib_major, lib_minor = _parse_major_minor(library_version)
    device_major, device_minor = _parse_major_minor(device_version)

    if lib_major > device_major:
        raise exceptions.BusyBarAPIVersionError(
            library_version=library_version,
            device_version=device_version,
            message="Device API is older than Busy Lib supports; please update firmware.",
        )

    if lib_major < device_major:
        raise exceptions.BusyBarAPIVersionError(
            library_version=library_version,
            device_version=device_version,
            message="Busy Lib is outdated for this device API; please update Busy Lib.",
        )

    if lib_minor > device_minor:
        raise exceptions.BusyBarAPIVersionError(
            library_version=library_version,
            device_version=device_version,
            message="Device API minor version is behind Busy Lib; please update firmware.",
        )
