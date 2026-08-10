from __future__ import annotations

import os
import re
import inspect
from collections.abc import Callable
from functools import wraps
from typing import Literal, TypeVar, cast

from . import exceptions

API_VERSION = os.environ.get("BUSY_API_VERSION", "25.0.0")
API_VERSION_HEADER = "X-Busy-Api-Version"
CompatibilityMode = Literal["warn", "strict", "none"]
F = TypeVar("F", bound=Callable[..., object])


class MethodCompatibility(dict[str, str]):
    """
    Dictionary metadata describing a client helper's OpenAPI compatibility.

    Carries the minimum `version` a helper targets, or a `status`:
    `"removed"` with the `replacement` to use instead, or `"experimental"`
    with a `note` about the firmware that introduces the endpoint.
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
    implementation targets. For most helpers that is the version in which
    the device endpoint first appeared, taken from the firmware's own route
    tables across release tags. Where a contract later changed in a
    breaking way, the higher version wins - `log_dump` targets 25.0.0 even
    though `/api/log_dump` exists from 24.3.0. When a method's request or
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


def removed_endpoint(
    *,
    path: str,
    method: str,
    replacement: str | None = None,
) -> Callable[[F], F]:
    """
    Mark a helper whose device endpoint no longer exists in any firmware.

    `requires_openapi` declares a *minimum* version, which can't express an
    endpoint that has been withdrawn: there is no newer firmware where the
    call starts working again. Marked helpers raise immediately with the
    replacement to use, instead of letting an opaque 404 come back from the
    device.
    """

    def decorator(func: F) -> F:
        metadata = MethodCompatibility(
            path=path,
            method=method,
            status="removed",
            **({"replacement": replacement} if replacement else {}),
        )

        def fail() -> None:
            raise exceptions.BusyBarRemovedEndpointError(
                path=path,
                method=method,
                replacement=replacement,
            )

        if inspect.iscoroutinefunction(func):
            # Keep the async signature, or the exception surfaces when the
            # coroutine is created rather than awaited - which leaves any
            # sibling coroutines in the same gather() un-awaited.
            @wraps(func)
            async def async_wrapper(*args: object, **kwargs: object) -> object:
                fail()

            wrapper: Callable[..., object] = async_wrapper
        else:

            @wraps(func)
            def sync_wrapper(*args: object, **kwargs: object) -> object:
                fail()

            wrapper = sync_wrapper

        setattr(wrapper, "__busy_openapi__", metadata)
        return cast(F, wrapper)

    return decorator


def experimental_endpoint(
    *,
    path: str,
    method: str,
    note: str,
) -> Callable[[F], F]:
    """
    Mark a helper whose device endpoint is not in released firmware yet.

    The counterpart to `requires_openapi`, for the other end of an endpoint's
    life: there is no minimum API version to state because no released
    firmware serves it, so a version floor would have to be invented. The
    call is left working - it succeeds against firmware that does have the
    endpoint - and the situation is recorded in the metadata instead, where
    `method_compatibility()` and the API reference can show it.

    `note` says which firmware work introduces the endpoint, so the marker
    can be replaced with a real version once that ships.
    """

    def decorator(func: F) -> F:
        setattr(
            func,
            "__busy_openapi__",
            MethodCompatibility(
                path=path,
                method=method,
                status="experimental",
                note=note,
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
