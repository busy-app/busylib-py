import dataclasses
import enum
import json
import typing as tp
import urllib.parse

import requests

from busylib import exceptions, types

JsonType = dict[str, tp.Any] | list[tp.Any] | str | int | float | bool | None


def _serialize_for_json(obj):
    if isinstance(obj, enum.Enum):
        return obj.value
    elif isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    elif dataclasses.is_dataclass(obj):
        return _serialize_for_json(dataclasses.asdict(obj))
    else:
        return obj


class BusyBar:
    """
    Main library class for interacting with the Busy Bar API.
    """

    def __init__(self, addr: str):
        self.base_url = f"http://{addr}"
        self.client = requests.Session()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.client.close()

    def _handle_response(
        self, response: requests.Response, as_bytes: bool = False
    ) -> bytes | str | JsonType:
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

        if as_bytes:
            return response.content

        try:
            return response.json()
        except json.JSONDecodeError:
            return response.text

    def get_version(self) -> types.VersionInfo:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/version")
        )
        data = self._handle_response(response)
        return types.VersionInfo(**data)

    def update_firmware(
        self, firmware_data: bytes, name: str | None = None
    ) -> types.SuccessResponse:
        params = {}
        if name:
            params["name"] = name

        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/update"),
            params=params,
            data=firmware_data,
            headers={"Content-Type": "application/octet-stream"},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def get_status(self) -> types.Status:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/status")
        )
        data = self._handle_response(response)

        system = None
        if data.get("system"):
            system = types.StatusSystem(**data["system"])

        power = None
        if data.get("power"):
            power_data = data["power"]

            if power_data.get("state"):
                power_data["state"] = types.PowerState(power_data["state"])

            power = types.StatusPower(**power_data)

        return types.Status(system=system, power=power)

    def get_system_status(self) -> types.StatusSystem:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/status/system")
        )
        data = self._handle_response(response)
        return types.StatusSystem(**data)

    def get_power_status(self) -> types.StatusPower:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/status/power")
        )
        data = self._handle_response(response)

        if data.get("state"):
            data["state"] = types.PowerState(data["state"])

        return types.StatusPower(**data)

    def write_storage_file(self, path: str, data: bytes) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/storage/write"),
            params={"path": path},
            data=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def read_storage_file(self, path: str) -> bytes:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/storage/read"),
            params={"path": path},
        )
        return self._handle_response(response, as_bytes=True)

    def list_storage_files(self, path: str) -> types.StorageList:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/storage/list"),
            params={"path": path},
        )
        data = self._handle_response(response)

        elements = []
        for item in data.get("list", []):
            if item["type"] == "file":
                elements.append(types.StorageFileElement(**item))
            elif item["type"] == "dir":
                elements.append(types.StorageDirElement(**item))

        return types.StorageList(list=elements)

    def remove_storage_file(self, path: str) -> types.SuccessResponse:
        response = self.client.delete(
            urllib.parse.urljoin(self.base_url, "/api/v0/storage/remove"),
            params={"path": path},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def create_storage_directory(self, path: str) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/storage/mkdir"),
            params={"path": path},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def upload_asset(
        self, app_id: str, filename: str, data: bytes
    ) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/assets/upload"),
            params={"app_id": app_id, "file": filename},
            data=data,
            headers={"Content-Type": "application/octet-stream"},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def delete_app_assets(self, app_id: str) -> types.SuccessResponse:
        response = self.client.delete(
            urllib.parse.urljoin(self.base_url, "/api/v0/assets/upload"),
            params={"app_id": app_id},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def draw_on_display(
        self, display_data: types.DisplayElements
    ) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/display/draw"),
            json=_serialize_for_json(display_data),
            headers={"Content-Type": "application/json"},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def clear_display(self) -> types.SuccessResponse:
        response = self.client.delete(
            urllib.parse.urljoin(self.base_url, "/api/v0/display/draw")
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def get_display_brightness(self) -> types.DisplayBrightnessInfo:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/display/brightness")
        )
        data = self._handle_response(response)
        return types.DisplayBrightnessInfo(**data)

    def set_display_brightness(
        self, front: str | None = None, back: str | None = None
    ) -> types.SuccessResponse:
        params = {}
        if front is not None:
            params["front"] = front
        if back is not None:
            params["back"] = back

        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/display/brightness"),
            params=params,
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def play_audio(self, app_id: str, path: str) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/audio/play"),
            params={"app_id": app_id, "path": path},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def stop_audio(self) -> types.SuccessResponse:
        response = self.client.delete(
            urllib.parse.urljoin(self.base_url, "/api/v0/audio/play")
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def get_audio_volume(self) -> types.AudioVolumeInfo:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/audio/volume")
        )
        data = self._handle_response(response)
        return types.AudioVolumeInfo(**data)

    def set_audio_volume(self, volume: float) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/audio/volume"),
            params={"volume": volume},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def send_input_key(self, key: types.InputKey) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/input"),
            params={"key": key.value},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def enable_wifi(self) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/wifi/enable")
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def disable_wifi(self) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/wifi/disable")
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def get_wifi_status(self) -> types.StatusResponse:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/wifi/status")
        )
        data = self._handle_response(response)

        if data.get("state"):
            data["state"] = types.WifiState(data["state"])

        if data.get("security"):
            data["security"] = types.WifiSecurityMethod(data["security"])

        if data.get("ip_config"):
            ip_config_data = data["ip_config"]
            if ip_config_data.get("ip_method"):
                ip_config_data["ip_method"] = types.WifiIpMethod(
                    ip_config_data["ip_method"]
                )
            if ip_config_data.get("ip_type"):
                ip_config_data["ip_type"] = types.WifiIpType(ip_config_data["ip_type"])
            data["ip_config"] = types.WifiIpConfig(**ip_config_data)

        return types.StatusResponse(**data)

    def connect_wifi(self, config: types.ConnectRequestConfig) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/wifi/connect"),
            json=_serialize_for_json(config),
            headers={"Content-Type": "application/json"},
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def disconnect_wifi(self) -> types.SuccessResponse:
        response = self.client.post(
            urllib.parse.urljoin(self.base_url, "/api/v0/wifi/disconnect")
        )
        data = self._handle_response(response)
        return types.SuccessResponse(**data)

    def scan_wifi_networks(self) -> types.NetworkResponse:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/wifi/networks")
        )
        data = self._handle_response(response)

        networks = []
        if data.get("networks"):
            for network_data in data["networks"]:
                if network_data.get("security"):
                    network_data["security"] = types.WifiSecurityMethod(
                        network_data["security"]
                    )

                networks.append(types.Network(**network_data))

        return types.NetworkResponse(
            count=data.get("count"),
            networks=networks or None,
        )

    def get_screen_frame(self, display: int) -> bytes:
        response = self.client.get(
            urllib.parse.urljoin(self.base_url, "/api/v0/screen"),
            params={"display": display},
        )
        return self._handle_response(response, as_bytes=True)
