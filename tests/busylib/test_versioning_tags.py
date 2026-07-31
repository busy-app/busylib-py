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
