import asyncio

from examples.bc.client_factory import build_client
from examples.bc.models import human_size


def test_human_size_formats_units() -> None:
    assert human_size(0) == "0B"
    assert human_size(1024) == "1.0K"
    assert human_size(1536) == "1.5K"


def test_build_client_adds_scheme(monkeypatch) -> None:
    monkeypatch.delenv("BUSYLIB_LAN_TOKEN", raising=False)
    monkeypatch.delenv("BUSY_LAN_TOKEN", raising=False)
    monkeypatch.delenv("BUSYLIB_CLOUD_TOKEN", raising=False)
    monkeypatch.delenv("BUSY_CLOUD_TOKEN", raising=False)

    client = build_client("10.0.0.1", None)
    try:
        assert client.base_url == "http://10.0.0.1"
    finally:
        asyncio.run(client.aclose())


def test_build_client_uses_lan_token(monkeypatch) -> None:
    monkeypatch.setenv("BUSYLIB_LAN_TOKEN", "lan-token")
    monkeypatch.delenv("BUSY_LAN_TOKEN", raising=False)
    monkeypatch.delenv("BUSYLIB_CLOUD_TOKEN", raising=False)
    monkeypatch.delenv("BUSY_CLOUD_TOKEN", raising=False)

    client = build_client("10.0.0.2", None)
    try:
        assert client.client.headers.get("x-api-token") == "lan-token"
    finally:
        asyncio.run(client.aclose())
