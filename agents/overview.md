# Busylib Python Client - Repository Overview

## Quick Facts
- Purpose: thin Python wrapper over Busy Bar HTTP API (display, audio, storage, Wi-Fi, BLE, firmware).
- Entry point: `busylib.BusyBar`; creates `requests.Session`, composes URLs from `base_url`.
- Models: enums plus `dataclasses` in `busylib/types.py` mirror API payloads; custom `BusyBarAPIError` in `busylib/exceptions.py`.
- Tooling: `pyproject.toml` (setuptools build, Python >=3.10, requests), `Makefile` helpers (`make test`, `format`, etc.), tests under `tests/`.

## Code Structure
- `busylib/__init__.py` - re-exports `BusyBar` for `from busylib import BusyBar`.
- `busylib/client.py` - BusyBar HTTP client:
  - Session setup: default base URL `http://10.0.4.20`; if only `token` given uses cloud proxy `https://proxy.dev.busy.app`; auth header injected when token provided.
  - `_serialize_for_json` converts enums/dataclasses/lists/dicts for JSON payloads.
  - `_handle_response` raises `BusyBarAPIError` on HTTP >=400 (prefers JSON error body), returns JSON/str/bytes.
  - Firmware: `get_version`, `update_firmware`.
  - Status: `get_status`, `get_system_status`, `get_power_status`.
  - Storage: `write_storage_file`, `read_storage_file`, `list_storage_files`, `remove_storage_file`, `create_storage_directory`.
  - Assets: `upload_asset`, `delete_app_assets`.
  - Display: `draw_on_display`, `clear_display`, `get_display_brightness`, `set_display_brightness`.
  - Audio: `play_audio`, `stop_audio`, `get_audio_volume`, `set_audio_volume`.
  - Input: `send_input_key`.
  - Wi-Fi: `get_wifi_status`, `connect_wifi`, `disconnect_wifi`, `scan_wifi_networks`.
  - Screen capture: `get_screen_frame`.
  - BLE: `ble_enable`, `ble_disable`, `ble_status`, `ble_forget_pairing`.
- `busylib/types.py` - enums plus dataclasses describing API payloads:
  - Wi-Fi (`WifiState`, `WifiSecurityMethod`, `WifiIpMethod`, `WifiIpType`, `WifiIpConfig`, `StatusResponse`, `Network`, `NetworkResponse`, `ConnectRequestConfig`).
  - Power/status (`PowerState`, `StatusSystem`, `StatusPower`, `Status`).
  - Storage (`StorageFileElement`, `StorageDirElement`, `StorageList`).
  - Display (`DisplayElementType`, `DisplayName`, `TextElement`, `ImageElement`, `DisplayElements`, `DisplayBrightnessInfo`).
  - Audio (`AudioVolumeInfo`).
  - General (`SuccessResponse`, `Error`, `VersionInfo`, `ScreenResponse`, `BleStatus`, `InputKey` enum).
- `busylib/exceptions.py` - `BusyBarAPIError` captures error text plus code, stringifies as `API Error: <error> (code: <code>)`.
- Tests (`tests/`) - pytest plus requests-mock:
  - `test_client_init.py` covers base URL/auth setup.
  - `test_client.py` exercises most HTTP methods, error handling, and an integration-style flow with mocked responses.
- Tooling/config: `pyproject.toml` (dependencies, ruff config), `Makefile` helpers, minimal `setup.py`, `README.md` with API examples.

## Notable Behaviors and Coverage
- URL handling uses `urllib.parse.urljoin` with `base_url` set once during init; no per-call IP validation.
- Requests reuse a single `requests.Session`; context manager (`with BusyBar(...)`) closes the session on exit.
- JSON serialization ensures enums and dataclasses are converted before sending (`draw_on_display`, Wi-Fi connect).
- Error pathway: any HTTP >=400 raises `BusyBarAPIError`; if response is not JSON, raw text is used.
- Tests mock endpoints without host prefix (for example `"/api/version"`), relying on requests-mock base URL matching; one integration test uses the full base.

## Gaps, Risks, and Potential Improvements
- Missing API methods versus tests: pytest expects `enable_wifi` and `disable_wifi`, but `BusyBar` implements only `get_wifi_status`, `connect_wifi`, `disconnect_wifi`, `scan_wifi_networks`. Tests will fail; either add the methods or adjust tests.
- README or typing mismatch: README examples reference `version_info.version`, but `VersionInfo` exposes `api_semver`; can confuse users and documentation accuracy.
- Error or model coverage: `VersionInfo` includes only `api_semver`, while API responses may also include other fields; decide whether to expand the dataclass or explicitly ignore extras.
- BLE and Wi-Fi method naming drift: BLE uses `ble_*` verbs; Wi-Fi uses mixed naming (connect/disconnect/scan) without enable/disable; align naming for API symmetry.
- No retries or timeouts: requests are made without timeouts or retry strategy; long-running calls may hang.
- Validation: inputs (IP address, volume range, brightness bounds, display elements) are not validated client-side; all validation deferred to the server.
- Serialization helper: `_serialize_for_json` handles enums and dataclasses but not pathlib objects or datetime; document expectations or extend if needed.
- Testing gaps: no coverage for BLE methods, `get_screen_frame`, or `delete_app_assets`; limited negative-path tests outside version endpoint.
- Makefile placeholders: `lint`, `test-cov`, `docs` targets are stubs; consider implementing or removing.

## Quick Start Flow
1) Instantiate `BusyBar(addr_or_none, token_optional)`.
2) Upload assets (`upload_asset`), draw UI (`draw_on_display`), play or stop audio, adjust brightness or volume.
3) Query device (`get_status`, `get_wifi_status`, `ble_status`), manage storage, and handle firmware updates via `update_firmware`.

