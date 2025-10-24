import pytest

from busylib import BusyBar


def test_busybar_init_local():
    bb = BusyBar()

    assert bb.base_url == "http://10.0.4.20"
    assert "Authorization" not in bb.client.headers


@pytest.mark.parametrize("addr", ["192.168.6.40", "http://192.168.6.40"])
def test_busybar_init_addr_http(addr: str):
    bb = BusyBar(addr)

    assert bb.base_url == "http://192.168.6.40"
    assert "Authorization" not in bb.client.headers


def test_busybar_init_addr_https():
    bb = BusyBar("https://secure.busy.app")

    assert bb.base_url == "https://secure.busy.app"
    assert "Authorization" not in bb.client.headers


def test_busybar_init_cloud_token():
    bb = BusyBar(token="some-token")

    assert bb.base_url == "https://proxy.dev.busy.app"
    assert bb.client.headers["Authorization"] == "Bearer some-token"


def test_busybar_init_addr_token():
    bb = BusyBar("https://proxy.example.net", token="another-token")

    assert bb.base_url == "https://proxy.example.net"
    assert bb.client.headers["Authorization"] == "Bearer another-token"
