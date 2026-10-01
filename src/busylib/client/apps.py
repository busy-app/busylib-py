from __future__ import annotations

import logging

import httpx2

from .. import types, versioning
from .base import AsyncClientBase, SyncClientBase

logger = logging.getLogger(__name__)

# The bar closes an upload that goes quiet for five seconds, and takes up
# to 100 MiB; a package is kilobytes, so this is about a slow link rather
# than a big file.
APP_UPLOAD_TIMEOUT = httpx2.Timeout(connect=10.0, read=60.0, write=60.0, pool=10.0)

_NOTE = "JavaScript applications arrive with firmware FW-1077 and later"
_APP_STREAM = "application/octet-stream"


class AppsMixin(SyncClientBase):
    """
    JavaScript applications: install, remove, launch and configure.

    Installing is two steps on purpose. `apps_stage` uploads a package and
    the bar unpacks it and reports what it found, including any version of
    the same application it would replace; `apps_install` then commits it
    with the key staging returned. Nothing changes on the bar between the
    two, which is what lets a caller show the difference and ask first.

    These endpoints answer on the local network only. They are not served
    through the cloud connection.
    """

    @versioning.experimental_endpoint(
        path="/api/apps/list",
        method="GET",
        note=_NOTE,
    )
    def apps_list(self) -> types.AppListResult:
        logger.info("apps_list")
        data = self._request("GET", "/api/apps/list")
        return types.AppListResult.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/stage",
        method="POST",
        note=_NOTE,
    )
    def apps_stage(
        self,
        package: bytes,
        *,
        timeout: float | httpx2.Timeout | None = APP_UPLOAD_TIMEOUT,
    ) -> types.AppStageResult:
        """
        Upload a package (a tar or tgz holding one application folder).

        The archive must contain the application as a single top-level
        folder - `<app id>/appmeta/manifest.json` and what it refers to.
        The bar looks at the first level only and takes the first folder
        that loads as an application.
        """
        logger.info("apps_stage size=%s", len(package))
        data = self._request(
            "POST",
            "/api/apps/stage",
            headers={"Content-Type": _APP_STREAM},
            data=package,
            timeout=timeout,
        )
        return types.AppStageResult.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/install",
        method="POST",
        note=_NOTE,
    )
    def apps_install(self, install_key: int) -> types.SuccessResponse:
        logger.info("apps_install")
        data = self._request(
            "POST",
            "/api/apps/install",
            params={"install_key": install_key},
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/launch",
        method="POST",
        note="Launching arrives with FW-1188",
    )
    def apps_launch(self, app_id: str) -> types.SuccessResponse:
        logger.info("apps_launch app_id=%s", app_id)
        data = self._request(
            "POST",
            "/api/apps/launch",
            params={"app_id": app_id},
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/quit",
        method="POST",
        note="Quitting arrives with FW-1189",
    )
    def apps_quit(self) -> types.SuccessResponse:
        """
        Leave the running application. The bar answers 409 when none is.
        """
        logger.info("apps_quit")
        data = self._request("POST", "/api/apps/quit")
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps",
        method="DELETE",
        note=_NOTE,
    )
    def apps_delete(self, app_id: str) -> types.SuccessResponse:
        """
        Remove an application, keeping its settings.
        """
        logger.info("apps_delete app_id=%s", app_id)
        data = self._request(
            "DELETE",
            "/api/apps",
            params={"app_id": app_id},
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/settings",
        method="GET",
        note="Application settings arrive with FW-1182",
    )
    def apps_settings(self, app_id: str) -> types.AppSettingsDocument:
        """
        The complete settings document; the first read creates it from the
        application's defaults.
        """
        logger.info("apps_settings app_id=%s", app_id)
        data = self._request(
            "GET",
            "/api/apps/settings",
            params={"app_id": app_id},
        )
        return types.AppSettingsDocument.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/settings",
        method="PUT",
        note="Application settings arrive with FW-1182",
    )
    def apps_settings_set(
        self, app_id: str, document: types.AppSettingsDocument
    ) -> types.SuccessResponse:
        """
        Replace the settings document.

        Every field has to be present and valid and the version has to match
        the application's; keys the application does not know are dropped.
        """
        logger.info("apps_settings_set app_id=%s", app_id)
        data = self._request(
            "PUT",
            "/api/apps/settings",
            params={"app_id": app_id},
            json_payload=document.model_dump(mode="json"),
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/settings",
        method="DELETE",
        note="Application settings arrive with FW-1182",
    )
    def apps_settings_reset(self, app_id: str) -> types.SuccessResponse:
        """
        Put every setting back to the application's default.
        """
        logger.info("apps_settings_reset app_id=%s", app_id)
        data = self._request(
            "DELETE",
            "/api/apps/settings",
            params={"app_id": app_id},
        )
        return types.SuccessResponse.model_validate(data)


class AsyncAppsMixin(AsyncClientBase):
    """
    Async JavaScript applications. See `AppsMixin`.
    """

    @versioning.experimental_endpoint(
        path="/api/apps/list",
        method="GET",
        note=_NOTE,
    )
    async def apps_list(self) -> types.AppListResult:
        logger.info("async apps_list")
        data = await self._request("GET", "/api/apps/list")
        return types.AppListResult.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/stage",
        method="POST",
        note=_NOTE,
    )
    async def apps_stage(
        self,
        package: bytes,
        *,
        timeout: float | httpx2.Timeout | None = APP_UPLOAD_TIMEOUT,
    ) -> types.AppStageResult:
        logger.info("async apps_stage size=%s", len(package))
        data = await self._request(
            "POST",
            "/api/apps/stage",
            headers={"Content-Type": _APP_STREAM},
            data=package,
            timeout=timeout,
        )
        return types.AppStageResult.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/install",
        method="POST",
        note=_NOTE,
    )
    async def apps_install(self, install_key: int) -> types.SuccessResponse:
        logger.info("async apps_install")
        data = await self._request(
            "POST",
            "/api/apps/install",
            params={"install_key": install_key},
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/launch",
        method="POST",
        note="Launching arrives with FW-1188",
    )
    async def apps_launch(self, app_id: str) -> types.SuccessResponse:
        logger.info("async apps_launch app_id=%s", app_id)
        data = await self._request(
            "POST",
            "/api/apps/launch",
            params={"app_id": app_id},
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/quit",
        method="POST",
        note="Quitting arrives with FW-1189",
    )
    async def apps_quit(self) -> types.SuccessResponse:
        logger.info("async apps_quit")
        data = await self._request("POST", "/api/apps/quit")
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps",
        method="DELETE",
        note=_NOTE,
    )
    async def apps_delete(self, app_id: str) -> types.SuccessResponse:
        logger.info("async apps_delete app_id=%s", app_id)
        data = await self._request(
            "DELETE",
            "/api/apps",
            params={"app_id": app_id},
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/settings",
        method="GET",
        note="Application settings arrive with FW-1182",
    )
    async def apps_settings(self, app_id: str) -> types.AppSettingsDocument:
        logger.info("async apps_settings app_id=%s", app_id)
        data = await self._request(
            "GET",
            "/api/apps/settings",
            params={"app_id": app_id},
        )
        return types.AppSettingsDocument.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/settings",
        method="PUT",
        note="Application settings arrive with FW-1182",
    )
    async def apps_settings_set(
        self, app_id: str, document: types.AppSettingsDocument
    ) -> types.SuccessResponse:
        logger.info("async apps_settings_set app_id=%s", app_id)
        data = await self._request(
            "PUT",
            "/api/apps/settings",
            params={"app_id": app_id},
            json_payload=document.model_dump(mode="json"),
        )
        return types.SuccessResponse.model_validate(data)

    @versioning.experimental_endpoint(
        path="/api/apps/settings",
        method="DELETE",
        note="Application settings arrive with FW-1182",
    )
    async def apps_settings_reset(self, app_id: str) -> types.SuccessResponse:
        logger.info("async apps_settings_reset app_id=%s", app_id)
        data = await self._request(
            "DELETE",
            "/api/apps/settings",
            params={"app_id": app_id},
        )
        return types.SuccessResponse.model_validate(data)
