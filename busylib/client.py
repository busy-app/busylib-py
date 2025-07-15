import requests
from typing import IO
from busylib.types import ApiResponse


class ApiClient:
    def __init__(self, base_url: str):
        if not base_url.endswith("/"):
            base_url += "/"
        self.base_url = base_url
        self.session = requests.Session()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, object] | None = None,
        json: object | None = None,
        data: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> ApiResponse:
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.request(
                method, url, params=params, json=json, data=data, headers=headers
            )
            response.raise_for_status()
            if response.status_code == 204 or not response.content:
                return None
            # We expect a JSON response that can be mapped to our dataclass
            data = response.json()
            return ApiResponse(
                success=data.get("success", True), message=data.get("message")
            )
        except requests.exceptions.RequestException as e:
            # Re-raise as a custom exception for better error handling upstream
            raise ConnectionError(f"API request failed: {e}") from e

    def post(
        self,
        endpoint: str,
        params: dict[str, object] = None,
        json: object | None = None,
        data: object | None = None,
        headers: dict[str, str] | None = None,
    ) -> ApiResponse | None:
        return self._request(
            "POST", endpoint, params=params, json=json, data=data, headers=headers
        )

    def get(
        self, endpoint: str, params: dict[str, object] | None = None
    ) -> ApiResponse | None:
        return self._request("GET", endpoint, params=params)

    def delete(
        self, endpoint: str, params: dict[str, object] | None = None
    ) -> ApiResponse | None:
        return self._request("DELETE", endpoint, params=params)

    def upload_asset(
        self, app_id: str, file_name: str, file: bytes | IO[bytes]
    ) -> ApiResponse | None:
        """
        Uploads an asset to the device.
        """
        payload = {"app_id": app_id, "file": file_name}
        headers = {"Content-Type": "application/octet-stream"}
        return self.post("v0/assets/upload", params=payload, data=file, headers=headers)

    def delete_assets(self, app_id: str) -> ApiResponse | None:
        """
        Deletes all assets for a specific application from the device.
        """
        params = {"app_id": app_id}
        return self.delete("v0/assets/upload", params=params)

    def play_audio(self, app_id: str, path: str) -> ApiResponse | None:
        """
        Plays an audio file from the assets directory.
        """
        params = {"app_id": app_id, "path": path}
        return self.post("v0/audio/play", params=params)

    def stop_audio(self) -> ApiResponse | None:
        """
        Stops any currently playing audio on the device.
        """
        return self.delete("v0/audio/play")

    def draw_display(
        self, app_id: str, elements: list[dict[str, object]]
    ) -> ApiResponse | None:
        """
        Draws elements on the device display.
        """
        default_values = {"timeout": 5, "x": 0, "y": 0, "display": "front"}

        normalized_elements = [default_values | e for e in elements]
        return self.post(
            "v0/display/draw", json={"app_id": app_id, "elements": normalized_elements}
        )

    def clear_display(self) -> ApiResponse | None:
        """
        Clears the device display.
        """
        return self.delete("v0/display/draw")
