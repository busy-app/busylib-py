from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Literal, TypeVar

from . import exceptions

API_VERSION = os.environ.get("BUSY_API_VERSION", "25.0.0")
API_VERSION_HEADER = "X-Busy-Api-Version"
CompatibilityMode = Literal["warn", "strict", "none"]
F = TypeVar("F", bound=Callable[..., object])


class MethodCompatibility(dict[str, str]):
    """
    Dictionary metadata describing when a client helper appeared in OpenAPI.
    """


def requires_openapi(
    version: str,
    *,
    path: str,
    method: str,
) -> Callable[[F], F]:
    """
    Attach declarative OpenAPI compatibility metadata to a client method.

    `version` is the minimum firmware OpenAPI version the current
    implementation targets, not necessarily the version in which the
    underlying device endpoint first appeared. When a method's request or
    response contract changes in a breaking, non-translatable way, bump this
    version to match the new contract rather than keeping the old value or
    adding a silent compatibility shim.
    """

    def decorator(func: F) -> F:
        setattr(
            func,
            "__busy_openapi__",
            MethodCompatibility(
                version=version,
                path=path,
                method=method,
            ),
        )
        return func

    return decorator


def get_method_compatibility(
    method: Callable[..., object],
) -> MethodCompatibility | None:
    """
    Return OpenAPI compatibility metadata attached to a client method.
    """
    target = getattr(method, "__func__", method)
    metadata = getattr(target, "__busy_openapi__", None)
    if isinstance(metadata, MethodCompatibility):
        return metadata
    return None


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


def compatibility_error(
    *,
    library_version: str,
    device_version: str,
) -> exceptions.BusyBarAPIVersionError | None:
    """
    Return compatibility error instead of raising it.
    """
    try:
        ensure_compatible(
            library_version=library_version,
            device_version=device_version,
        )
    except exceptions.BusyBarAPIVersionError as exc:
        return exc
    return None
