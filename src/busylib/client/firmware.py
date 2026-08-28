from __future__ import annotations

import logging

from .. import types, versioning
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)

LOG_DUMP_FILENAME_VERSION = "25.0.0"


def _log_dump_params(
    filename: str | None,
    path: str | None,
    device_is_current: bool | None,
) -> dict[str, str] | None:
    """
    Choose the log_dump query for the contract the device speaks.

    `device_is_current` is None when the bar's version is unknown; the request
    then goes out as asked, because refusing on a guess would be worse than
    letting the device answer.
    """
    if filename is not None and path is not None:
        raise ValueError(
            "log_dump takes filename (OpenAPI 25.0.0+) or path (earlier), not both"
        )
    if filename is not None:
        if device_is_current is False:
            raise ValueError(
                "this device predates OpenAPI 25.0.0 and takes path=, a full "
                "destination such as /ext/dump.log, rather than filename="
            )
        return {"filename": filename}
    if path is not None:
        if device_is_current is True:
            raise ValueError(
                "this device is on OpenAPI 25.0.0 or later and takes "
                "filename=, a bare name without an extension, rather than path="
            )
        return {"path": path}
    # Neither given: both contracts write to their own default.
    return None


def _handle_compatibility(
    *,
    mode: versioning.CompatibilityMode,
    library_version: str,
    device_version: str,
) -> None:
    """
    Apply configured API compatibility policy after `/api/version`.
    """
    if mode == "none":
        return

    error = versioning.compatibility_error(
        library_version=library_version,
        device_version=device_version,
    )
    if error is None:
        return
    if mode == "strict":
        raise error

    logger.warning("%s", error)


class FirmwareMixin(SyncClientBase):
    """
    Version, transport, system status, and system maintenance methods.
    """

    def version(self) -> types.VersionInfo:
        """
        Fetch API version info and validate compatibility.
        """
        logger.info("version")
        data = self._request("GET", "/api/version")
        version_info = types.VersionInfo.model_validate(data)
        if version_info.api_semver:
            self._device_api_version = version_info.api_semver
            _handle_compatibility(
                mode=self.compatibility_mode,
                library_version=self.api_version,
                device_version=version_info.api_semver,
            )
        return version_info

    @versioning.requires_openapi(
        "18.3.0",
        path="/api/transport",
        method="GET",
    )
    def transport(self) -> types.NetworkInterfaceInfo:
        """
        Fetch active network transport via GET /api/transport.
        """
        logger.info("transport")
        data = self._request("GET", "/api/transport")
        return types.NetworkInterfaceInfo.model_validate(data)

    def status(self) -> types.Status:
        """
        Fetch full device status via GET /api/status.
        """
        logger.info("status")
        data = self._request("GET", "/api/status")
        return types.Status.model_validate(data)

    @versioning.requires_openapi(
        "11.0.0",
        path="/api/status/device",
        method="GET",
    )
    def status_device(self) -> types.StatusDevice:
        """
        Fetch device manufacturing status via GET /api/status/device.
        """
        logger.info("status_device")
        data = self._request("GET", "/api/status/device")
        return types.StatusDevice.model_validate(data)

    @versioning.requires_openapi(
        "11.0.0",
        path="/api/status/firmware",
        method="GET",
    )
    def status_firmware(self) -> types.StatusFirmware:
        """
        Fetch firmware status via GET /api/status/firmware.
        """
        logger.info("status_firmware")
        data = self._request("GET", "/api/status/firmware")
        return types.StatusFirmware.model_validate(data)

    def status_system(self) -> types.StatusSystem:
        """
        Fetch runtime status via GET /api/status/system.
        """
        logger.info("status_system")
        data = self._request("GET", "/api/status/system")
        return types.StatusSystem.model_validate(data)

    def status_power(self) -> types.StatusPower:
        """
        Fetch power status via GET /api/status/power.
        """
        logger.info("status_power")
        data = self._request("GET", "/api/status/power")
        return types.StatusPower.model_validate(data)

    @versioning.requires_openapi("25.0.0", path="/api/log_dump", method="POST")
    def log_dump(
        self,
        filename: str | None = None,
        *,
        path: str | None = None,
    ) -> types.LogDumpResponse:
        """
        Dump the in-memory device log buffer to a storage file.

        The contract changed at OpenAPI 25.0.0 and the two are not
        translatable, so both are kept rather than one being dropped:

        - `filename` is a bare name matching `^[a-zA-Z0-9_-]+$`; the device
          adds the extension and the storage path. 25.0.0 and later.
        - `path` is a full destination path such as `/ext/dump.log`. Before
          25.0.0.

        With neither, the device writes to its own default and the request is
        identical on both, which is why plain `log_dump()` needs no version at
        all.

        When the device version is known - after `version()`, or from
        `device_api_version=` - asking for the wrong one raises here instead
        of being refused by the bar with a bare 400.
        """
        params = _log_dump_params(
            filename, path, self.device_at_least(LOG_DUMP_FILENAME_VERSION)
        )
        logger.info("log_dump params=%s", params)
        data = self._request(
            "POST",
            "/api/log_dump",
            params=params,
            allow_text=True,
        )
        if data == "":
            return types.LogDumpResponse(result="OK")
        return types.LogDumpResponse.model_validate(data)

    @versioning.requires_openapi(
        "0.3.0",
        path="/api/name",
        method="GET",
    )
    def name(self) -> types.DeviceNameResponse:
        """
        Fetch device name via GET /api/name.
        """
        logger.info("name")
        data = self._request("GET", "/api/name")
        return types.DeviceNameResponse.model_validate(data)

    @versioning.requires_openapi(
        "0.3.0",
        path="/api/name",
        method="POST",
    )
    def name_set(self, name: str) -> types.SuccessResponse:
        """
        Set device name via POST /api/name.
        """
        logger.info("name_set")
        payload = types.DeviceNameUpdate(name=name).model_dump()
        data = self._request(
            "POST",
            "/api/name",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.requires_openapi(
        "0.3.0",
        path="/api/time",
        method="GET",
    )
    def time(self) -> types.DeviceTimeResponse:
        """
        Fetch device time via GET /api/time.
        """
        logger.info("time")
        data = self._request("GET", "/api/time")
        return types.DeviceTimeResponse.model_validate(data)


class AsyncFirmwareMixin(AsyncClientBase):
    """
    Async variant of version, transport, and system status methods.
    """

    async def version(self) -> types.VersionInfo:
        """
        Fetch API version info and validate compatibility.
        """
        logger.info("async version")
        data = await self._request("GET", "/api/version")
        version_info = types.VersionInfo.model_validate(data)
        if version_info.api_semver:
            self._device_api_version = version_info.api_semver
            _handle_compatibility(
                mode=self.compatibility_mode,
                library_version=self.api_version,
                device_version=version_info.api_semver,
            )
        return version_info

    @versioning.requires_openapi(
        "18.3.0",
        path="/api/transport",
        method="GET",
    )
    async def transport(self) -> types.NetworkInterfaceInfo:
        """
        Fetch active network transport via GET /api/transport.
        """
        logger.info("async transport")
        data = await self._request("GET", "/api/transport")
        return types.NetworkInterfaceInfo.model_validate(data)

    async def status(self) -> types.Status:
        """
        Fetch full device status via GET /api/status.
        """
        logger.info("async status")
        data = await self._request("GET", "/api/status")
        return types.Status.model_validate(data)

    @versioning.requires_openapi(
        "11.0.0",
        path="/api/status/device",
        method="GET",
    )
    async def status_device(self) -> types.StatusDevice:
        """
        Fetch device manufacturing status via GET /api/status/device.
        """
        logger.info("async status_device")
        data = await self._request("GET", "/api/status/device")
        return types.StatusDevice.model_validate(data)

    @versioning.requires_openapi(
        "11.0.0",
        path="/api/status/firmware",
        method="GET",
    )
    async def status_firmware(self) -> types.StatusFirmware:
        """
        Fetch firmware status via GET /api/status/firmware.
        """
        logger.info("async status_firmware")
        data = await self._request("GET", "/api/status/firmware")
        return types.StatusFirmware.model_validate(data)

    async def status_system(self) -> types.StatusSystem:
        """
        Fetch runtime status via GET /api/status/system.
        """
        logger.info("async status_system")
        data = await self._request("GET", "/api/status/system")
        return types.StatusSystem.model_validate(data)

    async def status_power(self) -> types.StatusPower:
        """
        Fetch power status via GET /api/status/power.
        """
        logger.info("async status_power")
        data = await self._request("GET", "/api/status/power")
        return types.StatusPower.model_validate(data)

    @versioning.requires_openapi("25.0.0", path="/api/log_dump", method="POST")
    async def log_dump(
        self,
        filename: str | None = None,
        *,
        path: str | None = None,
    ) -> types.LogDumpResponse:
        """
        Dump the in-memory device log buffer to a storage file.

        The contract changed at OpenAPI 25.0.0 and the two are not
        translatable, so both are kept rather than one being dropped:

        - `filename` is a bare name matching `^[a-zA-Z0-9_-]+$`; the device
          adds the extension and the storage path. 25.0.0 and later.
        - `path` is a full destination path such as `/ext/dump.log`. Before
          25.0.0.

        With neither, the device writes to its own default and the request is
        identical on both, which is why plain `log_dump()` needs no version at
        all.

        When the device version is known - after `version()`, or from
        `device_api_version=` - asking for the wrong one raises here instead
        of being refused by the bar with a bare 400.
        """
        params = _log_dump_params(
            filename, path, self.device_at_least(LOG_DUMP_FILENAME_VERSION)
        )
        logger.info("async log_dump params=%s", params)
        data = await self._request(
            "POST",
            "/api/log_dump",
            params=params,
            allow_text=True,
        )
        if data == "":
            return types.LogDumpResponse(result="OK")
        return types.LogDumpResponse.model_validate(data)

    @versioning.requires_openapi(
        "0.3.0",
        path="/api/name",
        method="GET",
    )
    async def name(self) -> types.DeviceNameResponse:
        """
        Fetch device name via GET /api/name.
        """
        logger.info("async name")
        data = await self._request("GET", "/api/name")
        return types.DeviceNameResponse.model_validate(data)

    @versioning.requires_openapi(
        "0.3.0",
        path="/api/name",
        method="POST",
    )
    async def name_set(self, name: str) -> types.SuccessResponse:
        """
        Set device name via POST /api/name.
        """
        logger.info("async name_set")
        payload = types.DeviceNameUpdate(name=name).model_dump()
        data = await self._request(
            "POST",
            "/api/name",
            json_payload=payload,
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.requires_openapi(
        "0.3.0",
        path="/api/time",
        method="GET",
    )
    async def time(self) -> types.DeviceTimeResponse:
        """
        Fetch device time via GET /api/time.
        """
        logger.info("async time")
        data = await self._request("GET", "/api/time")
        return types.DeviceTimeResponse.model_validate(data)
