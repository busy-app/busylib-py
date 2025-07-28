import dataclasses
import enum
import json
import typing as tp

import requests

from busylib import exceptions
from busylib import types


class BusyBar:
    """
    Main library class for interacting with the Busy Bar API.
    """

    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.client = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.client.close()

    def _handle_response(self, response: requests.Response, expected_type: type = None):
        if response.status_code >= 400:
            try:
                error_data = response.json()
                raise exceptions.BusyBarAPIError(
                    error=error_data.get("error", "Unknown error"),
                    code=error_data.get("code", response.status_code),
                )
            except json.JSONDecodeError:
                raise exceptions.BusyBarAPIError(
                    error=f"HTTP {response.status_code}: {response.text}",
                    code=response.status_code,
                )

        if expected_type == bytes:
            return response.content

        try:
            data = response.json()
            if expected_type:
                if hasattr(expected_type, "__dataclass_fields__"):
                    return expected_type(**data)

                return expected_type(data) if data else None

            return data

        except json.JSONDecodeError:
            return response.text

    def get_version(self) -> types.VersionInfo:
        response = self.client.get(f"{self.base_url}/api/v0/version")
        return self._handle_response(response, types.VersionInfo)

    def update_firmware(
        self, firmware_data: bytes, name: str | None = None
    ) -> types.SuccessResponse:
        params = {}
        if name:
            params["name"] = name

        response = self.client.post(
            f"{self.base_url}/api/v0/update",
            params=params,
            data=firmware_data,
            headers={"Content-Type": "application/octet-stream"},
        )
        return self._handle_response(response, types.SuccessResponse)

    def get_status(self) -> types.Status:
        response = self.client.get(f"{self.base_url}/api/v0/status")
        return self._handle_response(response, types.Status)

    def get_system_status(self) -> types.StatusSystem:
        response = self.client.get(f"{self.base_url}/api/v0/status/system")
        return self._handle_response(response, types.StatusSystem)

    def get_power_status(self) -> types.StatusPower:
        response = self.client.get(f"{self.base_url}/api/v0/status/power")
        return self._handle_response(response, types.StatusPower)

    def write_storage_file(self, path: str, data: bytes) -> types.SuccessResponse:
        response = self.client.post(
            f"{self.base_url}/api/v0/storage/write",
            params={"path": path},
            data=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        return self._handle_response(response, types.SuccessResponse)

    def read_storage_file(self, path: str) -> bytes:
        response = self.client.get(
            f"{self.base_url}/api/v0/storage/read", params={"path": path}
        )
        return self._handle_response(response, bytes)

    def list_storage_files(self, path: str) -> types.StorageList:
        response = self.client.get(
            f"{self.base_url}/api/v0/storage/list", params={"path": path}
        )
        return self._handle_response(response, types.StorageList)

    def remove_storage_file(self, path: str) -> types.SuccessResponse:
        response = self.client.delete(
            f"{self.base_url}/api/v0/storage/remove", params={"path": path}
        )
        return self._handle_response(response, types.SuccessResponse)

    def create_storage_directory(self, path: str) -> types.SuccessResponse:
        response = self.client.post(
            f"{self.base_url}/api/v0/storage/mkdir", params={"path": path}
        )
        return self._handle_response(response, types.SuccessResponse)

    def upload_asset(
        self, app_id: str, filename: str, data: bytes
    ) -> types.SuccessResponse:
        response = self.client.post(
            f"{self.base_url}/api/v0/assets/upload",
            params={"app_id": app_id, "file": filename},
            data=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        return self._handle_response(response, types.SuccessResponse)

    def delete_app_assets(self, app_id: str) -> types.SuccessResponse:
        response = self.client.delete(
            f"{self.base_url}/api/v0/assets/upload", params={"app_id": app_id}
        )
        return self._handle_response(response, types.SuccessResponse)

    def draw_on_display(
        self, display_data: types.DisplayElements
    ) -> types.SuccessResponse:
        response = self.client.post(
            f"{self.base_url}/api/v0/display/draw",
            json=dataclasses.asdict(display_data),
            headers={"Content-Type": "application/json"},
        )
        return self._handle_response(response, types.SuccessResponse)

    def clear_display(self) -> types.SuccessResponse:
        response = self.client.delete(f"{self.base_url}/api/v0/display/draw")
        return self._handle_response(response, types.SuccessResponse)

    def get_display_brightness(self) -> types.DisplayBrightnessInfo:
        response = self.client.get(f"{self.base_url}/api/v0/display/brightness")
        return self._handle_response(response, types.DisplayBrightnessInfo)

    def set_display_brightness(
        self, front: str | None = None, back: str | None = None
    ) -> types.SuccessResponse:
        params = {}
        if front is not None:
            params["front"] = front
        if back is not None:
            params["back"] = back

        response = self.client.post(
            f"{self.base_url}/api/v0/display/brightness", params=params
        )
        return self._handle_response(response, types.SuccessResponse)

    def play_audio(self, app_id: str, path: str) -> types.SuccessResponse:
        response = self.client.post(
            f"{self.base_url}/api/v0/audio/play",
            params={"app_id": app_id, "path": path},
        )
        return self._handle_response(response, types.SuccessResponse)

    def stop_audio(self) -> types.SuccessResponse:
        response = self.client.delete(f"{self.base_url}/api/v0/audio/play")
        return self._handle_response(response, types.SuccessResponse)

    def get_audio_volume(self) -> types.AudioVolumeInfo:
        response = self.client.get(f"{self.base_url}/api/v0/audio/volume")
        return self._handle_response(response, types.AudioVolumeInfo)

    def set_audio_volume(self, volume: float) -> types.SuccessResponse:
        response = self.client.post(
            f"{self.base_url}/api/v0/audio/volume", params={"volume": volume}
        )
        return self._handle_response(response, types.SuccessResponse)

    def send_input_key(self, key: types.InputKey) -> types.SuccessResponse:
        response = self.client.post(
            f"{self.base_url}/api/v0/input", params={"key": key.value}
        )
        return self._handle_response(response, types.SuccessResponse)

    def enable_wifi(self) -> types.SuccessResponse:
        response = self.client.post(f"{self.base_url}/api/v0/wifi/enable")
        return self._handle_response(response, types.SuccessResponse)

    def disable_wifi(self) -> types.SuccessResponse:
        response = self.client.post(f"{self.base_url}/api/v0/wifi/disable")
        return self._handle_response(response, types.SuccessResponse)

    def get_wifi_status(self) -> types.StatusResponse:
        response = self.client.get(f"{self.base_url}/api/v0/wifi/status")
        return self._handle_response(response, types.StatusResponse)

    def connect_wifi(self, config: types.ConnectRequestConfig) -> types.SuccessResponse:
        response = self.client.post(
            f"{self.base_url}/api/v0/wifi/connect",
            json=dataclasses.asdict(config),
            headers={"Content-Type": "application/json"},
        )
        return self._handle_response(response, types.SuccessResponse)

    def disconnect_wifi(self) -> types.SuccessResponse:
        response = self.client.post(f"{self.base_url}/api/v0/wifi/disconnect")
        return self._handle_response(response, types.SuccessResponse)

    def scan_wifi_networks(self) -> types.NetworkResponse:
        response = self.client.get(f"{self.base_url}/api/v0/wifi/networks")
        return self._handle_response(response, types.NetworkResponse)

    def get_screen_frame(self, display: int) -> bytes:
        response = self.client.get(
            f"{self.base_url}/api/v0/screen", params={"display": display}
        )
        return self._handle_response(response, bytes)
