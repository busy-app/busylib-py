import requests
from typing import Optional, Any, Dict, Union, IO, List
from .types import ApiResponse


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
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
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
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Optional[ApiResponse]:
        return self._request(
            "POST", endpoint, params=params, json=json, data=data, headers=headers
        )

    def get(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[ApiResponse]:
        return self._request("GET", endpoint, params=params)

    def delete(
        self, endpoint: str, params: Optional[Dict[str, Any]] = None
    ) -> Optional[ApiResponse]:
        return self._request("DELETE", endpoint, params=params)

    def upload_asset(
        self, app_id: str, file_name: str, file: Union[bytes, IO[bytes]]
    ) -> Optional[ApiResponse]:
        """
        Uploads an asset to the device.
        """
        params = {"app_id": app_id, "file": file_name}
        headers = {"Content-Type": "application/octet-stream"}
        return self.post("v0/assets/upload", params=params, data=file, headers=headers)

    def delete_assets(self, app_id: str) -> Optional[ApiResponse]:
        """
        Deletes all assets for a specific application from the device.
        """
        params = {"app_id": app_id}
        return self.delete("v0/assets/upload", params=params)

    def play_audio(self, app_id: str, path: str) -> Optional[ApiResponse]:
        """
        Plays an audio file from the assets directory.
        """
        params = {"app_id": app_id, "path": path}
        return self.post("v0/audio/play", params=params)

    def stop_audio(self) -> Optional[ApiResponse]:
        """
        Stops any currently playing audio on the device.
        """
        return self.delete("v0/audio/play")

    def draw_display(
        self, app_id: str, elements: List[Dict[str, Any]]
    ) -> Optional[ApiResponse]:
        """
        Draws elements on the device display.
        """
        default_values = {"timeout": 5, "x": 0, "y": 0, "display": "front"}

        def with_defaults(element: Dict[str, Any]) -> Dict[str, Any]:
            return {**default_values, **element}

        normalized_elements = [with_defaults(e) for e in elements]
        return self.post(
            "v0/display/draw", json={"app_id": app_id, "elements": normalized_elements}
        )

    def clear_display(self) -> Optional[ApiResponse]:
        """
        Clears the device display.
        """
        return self.delete("v0/display/draw")
