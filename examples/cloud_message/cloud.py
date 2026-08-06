from __future__ import annotations

import logging
from contextlib import AbstractContextManager
from types import TracebackType
from typing import Any

import httpx

from busylib import BusyBar, types

logger = logging.getLogger(__name__)

# Documented at https://docs.busy.app/bar/dev/http-api ("via internet").
CLOUD_BASE_URL = "https://api.busy.app/busybar"


class CloudBar(AbstractContextManager["CloudBar"]):
    """
    Talk to a BUSY Bar over the internet instead of USB or the LAN.

    `BusyBar(token=...)` already selects cloud mode and sets the bearer header,
    but the cloud service exposes the device API under `/busybar/<endpoint>`
    rather than the on-device `/api/<endpoint>`. So requests are built with
    `prepare_request()` and executed against a client bound to the cloud base
    URL -- the documented hook for custom transports, which keeps busylib's
    error mapping and retry behaviour.
    """

    def __init__(
        self,
        token: str,
        *,
        base_url: str = CLOUD_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._bar = BusyBar(token=token)
        # Reuse the headers busylib built (bearer auth plus API version), so
        # the cloud client stays in sync with the library's expectations.
        self._cloud = httpx.Client(
            base_url=base_url,
            headers=dict(self._bar.client.headers),
            timeout=timeout,
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """
        Release both the busylib client and the cloud transport.
        """
        self._cloud.close()
        self._bar.close()

    def status(self) -> Any:
        """
        Fetch the device status snapshot, confirming the bar is reachable.
        """
        return self._request("GET", "/status")

    def draw(self, elements: types.DisplayElements) -> Any:
        """
        Draw display elements on the bar.
        """
        logger.info("draw application_name=%s", elements.application_name)
        return self._request(
            "POST",
            "/display/draw",
            json_payload=elements.model_dump(exclude_none=True),
        )

    def clear(self, application_name: str) -> Any:
        """
        Remove the elements this application drew.
        """
        logger.info("clear application_name=%s", application_name)
        return self._request(
            "DELETE",
            "/display/draw",
            params={"application_name": application_name},
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, object] | None = None,
        json_payload: Any | None = None,
    ) -> Any:
        prepared = self._bar.prepare_request(
            method,
            path,
            params=params,
            json_payload=json_payload,
        )
        result = self._bar.execute_prepared_request(prepared, client=self._cloud)
        return result
