import dataclasses

import pytest
import requests

from busylib import BusyBar
from busylib import exceptions
from busylib import types


@pytest.fixture
def addr():
    return "test-device.local"


@pytest.fixture
def client(addr):
    return BusyBar(addr)


@pytest.fixture
def sample_version_info():
    return types.VersionInfo(
        branch="main",
        version="1.2.0",
        build_date="2024-01-15",
        commit_hash="abc123def456"
    )


@pytest.fixture
def sample_status():
    return types.Status(
        system=types.StatusSystem(version="1.2.0", uptime="1d 6h 30m 15s"),
        power=types.StatusPower(
            state=types.PowerState.DISCHARGING,
            battery_charge=85,
            battery_voltage=4150,
            battery_current=-150,
            usb_voltage=5000
        )
    )


@pytest.fixture
def sample_storage_list():
    return types.StorageList(
        list=[
            types.StorageFileElement(type="file", name="test.png", size=1024),
            types.StorageDirElement(type="dir", name="assets"),
            types.StorageFileElement(type="file", name="config.json", size=512)
        ]
    )


@pytest.fixture
def sample_display_elements():
    return types.DisplayElements(
        app_id="test_app",
        elements=[
            types.TextElement(
                id="text1",
                type="text",
                x=10, y=20,
                text="Hello World",
                display=types.DisplayName.FRONT
            ),
            types.ImageElement(
                id="img1",
                type="image",
                x=0, y=40,
                path="logo.png",
                display=types.DisplayName.BACK
            )
        ]
    )


@pytest.fixture
def sample_wifi_config():
    return types.ConnectRequestConfig(
        ssid="TestNetwork",
        password="testpass123",
        security=types.WifiSecurityMethod.WPA2,
        ip_config=None
    )


def test_get_version_success(requests_mock, sample_version_info, client):
    url = "/api/v0/version"
    requests_mock.get(url, json={
        "branch": sample_version_info.branch,
        "version": sample_version_info.version,
        "build_date": sample_version_info.build_date,
        "commit_hash": sample_version_info.commit_hash
    })

    result = client.get_version()

    assert isinstance(result, types.VersionInfo)
    assert result.version == "1.2.0"
    assert result.branch == "main"


def test_get_version_error(requests_mock, client):
    url = "/api/v0/version"
    requests_mock.get(url, json={"error": "Internal server error", "code": 500}, status_code=500)

    with pytest.raises(exceptions.BusyBarAPIError) as exc_info:
        client.get_version()

    assert exc_info.value.code == 500
    assert "Internal server error" in str(exc_info.value)


def test_update_firmware_success(requests_mock, client):
    url = "/api/v0/update"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.update_firmware(b"fake-firmware-data", name="firmware")

    assert isinstance(resp, types.SuccessResponse)
    assert resp.result == "OK"

def test_get_status_success(requests_mock, sample_status, client):
    url = "/api/v0/status"
    requests_mock.get(url, json={
        "system": {
            "version": sample_status.system.version,
            "uptime": sample_status.system.uptime,
        },
        "power": {
            "state": sample_status.power.state.value,
            "battery_charge": sample_status.power.battery_charge,
            "battery_voltage": sample_status.power.battery_voltage,
            "battery_current": sample_status.power.battery_current,
            "usb_voltage": sample_status.power.usb_voltage,
        }
    })

    resp = client.get_status()

    assert isinstance(resp, types.Status)
    assert resp.power.battery_charge == 85
    assert resp.system.version == "1.2.0"


def test_write_storage_file_success(requests_mock, client):
    url = "/api/v0/storage/write"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.write_storage_file("/file.txt", b"test")

    assert isinstance(resp, types.SuccessResponse)
    assert resp.result == "OK"

def test_read_storage_file_success(requests_mock, client):
    url = "/api/v0/storage/read"
    content = b"some-binary-contents"
    requests_mock.get(url, content=content)

    resp = client.read_storage_file("/file.txt")

    assert resp == content

def test_list_storage_files_success(requests_mock, sample_storage_list, client):
    url = "/api/v0/storage/list"
    requests_mock.get(url, json=dataclasses.asdict(sample_storage_list))

    resp = client.list_storage_files("/ext")

    assert isinstance(resp, types.StorageList)
    assert len(resp.list) == 3


def test_remove_storage_file_success(requests_mock, client):
    url = "/api/v0/storage/remove"
    requests_mock.delete(url, json={"result": "OK"})

    resp = client.remove_storage_file("/file.txt")

    assert isinstance(resp, types.SuccessResponse)


def test_create_storage_directory_success(requests_mock, client):
    url = "/api/v0/storage/mkdir"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.create_storage_directory("/new_dir")

    assert isinstance(resp, types.SuccessResponse)


def test_draw_on_display_success(requests_mock, sample_display_elements, client):
    url = "/api/v0/display/draw"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.draw_on_display(sample_display_elements)

    assert isinstance(resp, types.SuccessResponse)

def test_clear_display_success(requests_mock, client):
    url = "/api/v0/display/draw"
    requests_mock.delete(url, json={"result": "OK"})

    resp = client.clear_display()

    assert isinstance(resp, types.SuccessResponse)

def test_get_display_brightness_success(requests_mock, client):
    url = "/api/v0/display/brightness"
    requests_mock.get(url, json={"front": "auto", "back": "50"})

    resp = client.get_display_brightness()

    assert isinstance(resp, types.DisplayBrightnessInfo)
    assert resp.front == "auto"
    assert resp.back == "50"

def test_set_display_brightness_success(requests_mock, client):
    url = "/api/v0/display/brightness"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.set_display_brightness(front="100", back="auto")

    assert isinstance(resp, types.SuccessResponse)


def test_play_audio_success(requests_mock, client):
    url = "/api/v0/audio/play"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.play_audio("test_app", "notify.snd")
    assert isinstance(resp, types.SuccessResponse)

def test_stop_audio_success(requests_mock, client):
    url = "/api/v0/audio/play"
    requests_mock.delete(url, json={"result": "OK"})

    resp = client.stop_audio()
    assert isinstance(resp, types.SuccessResponse)

def test_get_audio_volume_success(requests_mock, client):
    url = "/api/v0/audio/volume"
    requests_mock.get(url, json={"volume": 73.3})

    resp = client.get_audio_volume()

    assert isinstance(resp, types.AudioVolumeInfo)
    assert resp.volume == 73.3

def test_set_audio_volume_success(requests_mock, client):
    url = "/api/v0/audio/volume"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.set_audio_volume(12.0)

    assert isinstance(resp, types.SuccessResponse)


def test_enable_wifi_success(requests_mock, client):
    url = "/api/v0/wifi/enable"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.enable_wifi()

    assert isinstance(resp, types.SuccessResponse)

def test_disable_wifi_success(requests_mock, client):
    url = "/api/v0/wifi/disable"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.disable_wifi()

    assert isinstance(resp, types.SuccessResponse)

def test_get_wifi_status_success(requests_mock, client):
    url = "/api/v0/wifi/status"
    requests_mock.get(url, json={
        "state": "connected",
        "ssid": "TestNetwork",
        "security": "WPA2",
        "ip_config": {
            "ip_method": "dhcp",
            "ip_type": "ipv4",
            "address": "192.168.1.100"
        }
    })

    resp = client.get_wifi_status()

    assert isinstance(resp, types.StatusResponse)
    assert resp.state.value == "connected"
    assert resp.ssid == "TestNetwork"

def test_connect_wifi_success(requests_mock, sample_wifi_config, client):
    url = "/api/v0/wifi/connect"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.connect_wifi(sample_wifi_config)

    assert isinstance(resp, types.SuccessResponse)

def test_disconnect_wifi_success(requests_mock, client):
    url = "/api/v0/wifi/disconnect"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.disconnect_wifi()

    assert isinstance(resp, types.SuccessResponse)

def test_scan_wifi_networks_success(requests_mock, client):
    url = "/api/v0/wifi/networks"
    requests_mock.get(url, json={
        "count": 2,
        "networks": [
            {"ssid": "Network1", "security": "WPA2", "rssi": -45},
            {"ssid": "Network2", "security": "Open", "rssi": -60}
        ]
    })

    resp = client.scan_wifi_networks()

    assert isinstance(resp, types.NetworkResponse)
    assert resp.count == 2
    assert len(resp.networks) == 2


@pytest.mark.parametrize("key", [types.InputKey.UP, types.InputKey.DOWN, types.InputKey.OK, types.InputKey.BACK])
def test_send_input_key_success(requests_mock, key, client):
    url = "/api/v0/input"
    requests_mock.post(url, json={"result": "OK"})

    resp = client.send_input_key(key)

    assert isinstance(resp, types.SuccessResponse)


def test_http_404_error(requests_mock, client):
    url = "/api/v0/version"
    requests_mock.get(url, json={"error": "Not found", "code": 404}, status_code=404)

    with pytest.raises(exceptions.BusyBarAPIError) as exc:
        client.get_version()

    assert exc.value.code == 404

def test_http_500_error_without_json(requests_mock, client):
    url = "/api/v0/version"
    requests_mock.get(url, text="Internal Server Error", status_code=500)

    with pytest.raises(exceptions.BusyBarAPIError) as exc:
        client.get_version()

    assert "HTTP 500" in exc.value.error
    assert exc.value.code == 500


def test_requests_connection_error(monkeypatch, client):
    def fake_get(*a, **kw):
        raise requests.ConnectionError("fail")

    monkeypatch.setattr(requests.Session, "get", fake_get)

    with pytest.raises(requests.ConnectionError):
        client.get_version()


def test_integration_workflow(requests_mock, client):
    base = "http://test-device.local"
    requests_mock.get(f"{base}/api/v0/version", json={
        "branch": "main",
        "version": "1.0.0",
        "build_date": "2024-01-01",
        "commit_hash": "abc123"
    })
    requests_mock.post(f"{base}/api/v0/assets/upload", json={"result": "OK"})
    requests_mock.post(f"{base}/api/v0/display/draw", json={"result": "OK"})
    requests_mock.post(f"{base}/api/v0/audio/play", json={"result": "OK"})

    version = client.get_version()
    assert version.version == "1.0.0"

    resp_asset = client.upload_asset("test_app", "logo.png", b"img")
    assert resp_asset.result == "OK"

    display_elements = types.DisplayElements(
        app_id="test_app",
        elements=[types.TextElement(
            id="1", type="text", x=0, y=0, text="Test", display=types.DisplayName.FRONT
        )]
    )
    resp_disp = client.draw_on_display(display_elements)
    assert resp_disp.result == "OK"

    resp_audio = client.play_audio("test_app", "sound.snd")
    assert resp_audio.result == "OK"
