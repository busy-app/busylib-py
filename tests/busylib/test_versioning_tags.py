from __future__ import annotations

import pytest

from busylib import AsyncBusyBar, BusyBar, versioning

# Sampled from the firmware's route tables across release tags: the API
# version whose firmware first served each endpoint.
EXPECTED = {
    "ble_status": "0.3.0",
    "name_set": "0.3.0",
    "account_link": "1.0.0",
    "update_check": "4.1.0",
    "account_info": "4.1.0",
    "status_firmware": "11.0.0",
    "storage_rename": "11.0.0",
    "time_timezone_list": "11.0.0",
    "smart_home_switch": "18.3.0",
    "account_backend": "23.0.0",
    # Endpoint exists from 24.3.0, but the contract was reworked in 25.0.0.
    "log_dump": "25.0.0",
    # busybar-firmware#886, first released in firmware 1.2.3.
    "access_tokens_list": "27.5.0",
    "access_token_mint": "27.5.0",
    "access_tokens_delete_all": "27.5.0",
    "access_tokens_revoke": "27.5.0",
}


@pytest.mark.parametrize("name,version", sorted(EXPECTED.items()))
@pytest.mark.parametrize("client", [BusyBar, AsyncBusyBar])
def test_methods_declare_the_api_version_that_introduced_them(
    client: type, name: str, version: str
) -> None:
    """
    Compatibility tags match the firmware release that added the endpoint.
    """
    metadata = versioning.get_method_compatibility(getattr(client, name))

    assert metadata is not None, f"{name} carries no compatibility metadata"
    assert metadata["version"] == version


@pytest.mark.parametrize("client", [BusyBar, AsyncBusyBar])
def test_endpoints_present_since_the_first_api_are_left_untagged(
    client: type,
) -> None:
    """
    Helpers available in every firmware carry no version requirement.

    Tagging them would imply a floor that never applied.
    """
    for name in ("display_draw", "audio_play", "storage_write", "version"):
        assert versioning.get_method_compatibility(getattr(client, name)) is None


ACCESS_TOKEN_HELPERS = [
    "access_tokens_list",
    "access_token_mint",
    "access_tokens_delete_all",
    "access_tokens_revoke",
]


def test_the_experimental_marker_records_a_note_instead_of_a_version() -> None:
    """
    The marker carries a note where a version floor would go.

    No client helper needs it right now - the access-token endpoints it used
    to cover shipped in firmware 1.2.3 and carry a real floor - so it is
    exercised directly, and stays ready for the next unreleased endpoint.
    """

    @versioning.experimental_endpoint(
        path="/api/future",
        method="GET",
        note="busy-app/busybar-firmware#1234, not released yet",
    )
    def helper() -> None: ...

    metadata = versioning.get_method_compatibility(helper)

    assert metadata is not None
    assert metadata["status"] == "experimental"
    assert "version" not in metadata
    assert "1234" in metadata["note"]


@pytest.mark.parametrize("name", ACCESS_TOKEN_HELPERS)
def test_access_token_helpers_call_the_device(name: str) -> None:
    """
    Each helper reaches its own endpoint under /api/access/tokens.
    """
    import httpx2

    seen: list[str] = []

    bodies = {
        "access_tokens_list": {"tokens": []},
        "access_token_mint": {
            "short_id": "ab",
            "display_id": "abcd",
            "name": "x",
            "created_at": 0,
            "last_used_at": 0,
        },
        "access_tokens_delete_all": {"result": "OK"},
        "access_tokens_revoke": {"result": "OK"},
    }

    def responder(request: httpx2.Request) -> httpx2.Response:
        seen.append(request.url.path)
        return httpx2.Response(200, json=bodies[name])

    client = BusyBar(
        addr="http://device.local", transport=httpx2.MockTransport(responder)
    )
    getattr(client, name)("x") if name in (
        "access_token_mint",
        "access_tokens_revoke",
    ) else getattr(client, name)()

    assert seen and seen[0].startswith("/api/access/tokens")
