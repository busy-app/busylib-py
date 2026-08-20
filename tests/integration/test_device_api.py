"""
The functional surface, exercised against a real bar over every transport.

These are deliberately coarse: one test per area of behaviour rather than one
per endpoint. A real device is the only thing that can tell us the payloads
are right, and a hundred single-call tests against it would take minutes to
tell us less.

Anything written here is namespaced under a test application name and a test
storage directory, and every value that gets changed is put back.
"""

from __future__ import annotations

import io
import re
import time
import wave

import pytest
from PIL import Image

from busylib import types

from .conftest import APP_NAME, STORAGE_DIR

pytestmark = pytest.mark.integration


def test_identity_reads_agree_with_each_other(bar) -> None:
    """
    The bar reports a version, and status repeats it consistently.

    `/api/version` carries only `api_semver`; the human-readable firmware
    version lives under `/api/status`, which is exactly the split that made
    the setup wizard report "Firmware ?".
    """
    version = bar.version()
    status = bar.status()

    assert version.api_semver, "a bar must report its API version"
    assert status.device is not None and status.device.serial_number
    assert status.firmware is not None and status.firmware.version

    if status.system is not None and status.system.api_semver:
        assert status.system.api_semver == version.api_semver


def test_subsystem_state_is_readable(bar) -> None:
    """
    Every read-only subsystem answers with a parseable model.

    Grouped on purpose: these are the calls a dashboard makes on startup, and
    what matters is that none of them fail against real firmware.
    """
    assert bar.name().name
    assert bar.time() is not None
    assert bar.display_brightness().value is not None
    assert bar.audio_volume().volume is not None
    assert bar.wifi_status().state is not None
    assert bar.ble_status() is not None
    assert bar.storage_status() is not None
    assert bar.access() is not None
    assert bar.update_status() is not None
    assert bar.busy_snapshot() is not None


@pytest.mark.parametrize(
    "display,x,y",
    [(types.DisplayName.FRONT, 2, 4), (types.DisplayName.BACK, 4, 8)],
)
def test_draws_then_clears(
    free_display, bar, display: types.DisplayName, x: int, y: int
) -> None:
    """
    Text reaches both displays and the drawing can be withdrawn again.
    """
    elements = types.DisplayElements(
        application_name=APP_NAME,
        elements=[
            types.TextElement(
                id="probe",
                type="text",
                x=x,
                y=y,
                text="TEST",
                font="small",
                display=display,
            )
        ],
    )

    assert bar.display_draw(elements).result == "OK"
    assert bar.display_clear(application_name=APP_NAME).result == "OK"


def test_screen_returns_a_frame_of_the_expected_size(bar) -> None:
    """
    Both displays hand back a decodable frame.

    The size is fixed by the panel, so a mismatch means the decode path is
    wrong rather than the picture being different - which is how base64 was
    once rendered as pixels.
    """
    front = bar.screen(0)
    back = bar.screen(1)

    # Both come back as three bytes per pixel. The back panel shows 16 greys,
    # but the frame is not packed - assuming one byte per pixel here is how a
    # decode bug hides.
    assert len(front) == 72 * 16 * 3, "front is 72x16, three bytes per pixel"
    assert len(back) == 160 * 80 * 3, "back is 160x80, three bytes per pixel"


def test_a_drawn_colour_reads_back_as_itself(free_display, bar) -> None:
    """
    Red drawn on the bar comes back as red, not blue.

    The device orders the three colour bytes BGR while its own protobuf enum
    calls that format RGB888, so the library swaps them. Nothing but a real bar can
    catch that: a mock returns whatever bytes the test invented.
    """
    import collections

    for colour, expected in (
        ("#FF0000FF", (255, 0, 0)),
        ("#0000FFFF", (0, 0, 255)),
        ("#00FF00FF", (0, 255, 0)),
    ):
        bar.display_draw(
            types.DisplayElements(
                application_name=APP_NAME,
                elements=[
                    types.RectangleElement(
                        id="fill",
                        type="rectangle",
                        x=0,
                        y=0,
                        width=72,
                        height=16,
                        fill="solid",
                        fill_colors=[colour],
                        display=types.DisplayName.FRONT,
                    )
                ],
            )
        )
        time.sleep(1.2)

        frame = bar.screen(0)
        pixels = [tuple(frame[i : i + 3]) for i in range(0, len(frame), 3)]
        dominant, _ = collections.Counter(pixels).most_common(1)[0]

        assert dominant == expected, f"drew {colour}, frame says {dominant}"

    bar.display_clear(application_name=APP_NAME)


def test_storage_round_trip(bar) -> None:
    """
    Write, read back, list, rename and remove under /ext.

    Paths outside /ext are not refused with an error - the device stops
    answering - so the prefix is part of the contract, not a convention.
    """
    from busylib import exceptions

    payload = b"integration"
    path = f"{STORAGE_DIR}/probe.txt"
    renamed = f"{STORAGE_DIR}/probe-renamed.txt"

    try:
        bar.storage_mkdir(path=STORAGE_DIR)
    except exceptions.BusyBarAPIError as exc:
        # mkdir answers 400 when the directory is already there, so a rerun
        # after a failed run must not trip over its own leftovers.
        assert exc.status_code == 400, exc
    assert bar.storage_write(path=path, data=payload).result == "OK"
    assert bar.storage_read(path=path) == payload

    listing = bar.storage_list(path=STORAGE_DIR)
    assert any(item.name == "probe.txt" for item in listing.list)

    bar.storage_rename(old_path=path, new_path=renamed)
    assert bar.storage_read(path=renamed) == payload

    # Directories are removed by the same call as files.
    bar.storage_remove(path=renamed)
    bar.storage_remove(path=STORAGE_DIR)


def test_assets_and_audio(free_display, bar) -> None:
    """
    Upload an image and a sound, use both, then delete them together.

    `assets_delete` is scoped to the application name, so this cannot touch
    anything the user put on the bar under a different one.
    """
    from busylib import converter, exceptions

    buffer = io.BytesIO()
    Image.new("RGB", (72, 16), (0, 40, 0)).save(buffer, format="PNG")
    image_name, image_payload = converter.convert_for_storage(
        "probe.png", buffer.getvalue()
    )
    assert (
        bar.assets_upload(
            application_name=APP_NAME, filename=image_name, data=image_payload
        ).result
        == "OK"
    )

    audio = io.BytesIO()
    with wave.open(audio, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(b"\x00\x00" * 1600)
    audio_name, audio_payload = converter.convert_for_storage(
        "probe.wav", audio.getvalue()
    )
    bar.assets_upload(
        application_name=APP_NAME, filename=audio_name, data=audio_payload
    )

    bar.display_draw(
        types.DisplayElements(
            application_name=APP_NAME,
            elements=[
                types.ImageElement(
                    id="pic",
                    type="image",
                    x=0,
                    y=0,
                    path=image_name,
                    display=types.DisplayName.BACK,
                )
            ],
        )
    )
    assert bar.audio_play(application_name=APP_NAME, path=audio_name).result == "OK"
    try:
        bar.audio_stop()
    except exceptions.BusyBarAPIError as exc:
        # A short clip can finish before the stop lands, and the device
        # answers 410 rather than treating it as a no-op.
        assert exc.status_code == 410, exc

    bar.display_clear(application_name=APP_NAME)
    assert bar.assets_delete(application_name=APP_NAME).result == "OK"


def test_brightness_round_trip(bar) -> None:
    """
    A written brightness is read back, then the original is restored.

    The read lags the write by about a second on current firmware, so this
    polls rather than asserting immediately.
    """
    import time

    original = bar.display_brightness().value
    try:
        bar.display_brightness_set(50)
        for _ in range(10):
            if bar.display_brightness().value == "50":
                break
            time.sleep(0.5)
        assert bar.display_brightness().value == "50"
    finally:
        if original is not None:
            bar.display_brightness_set("auto" if original == "auto" else int(original))


def test_volume_round_trip(bar) -> None:
    """
    Volume survives a write and is restored afterwards.
    """
    original = bar.audio_volume().volume
    try:
        bar.audio_volume_set(42)
        assert bar.audio_volume().volume == 42
    finally:
        if original is not None:
            bar.audio_volume_set(int(original))


def test_device_name_round_trip(bar) -> None:
    """
    The name can be changed and put back.

    Discovery advertises this name, so leaving a test value behind would be
    visible on the network and in the owner's app.
    """
    original = bar.name().name
    probe = "busylib itest"
    try:
        assert bar.name_set(probe).result == "OK"
        assert bar.name().name == probe
    finally:
        if original:
            bar.name_set(original)
            assert bar.name().name == original


def test_input_is_accepted(bar) -> None:
    """
    Forwarded key presses are accepted for every button.
    """
    for key in (types.InputKey.OK, types.InputKey.BACK, types.InputKey.START):
        assert bar.input(key).result == "OK"


def test_compatibility_metadata_matches_this_bar(bar) -> None:
    """
    What the library claims about an endpoint holds against real firmware.

    An `experimental` marker means "no released firmware serves this yet", so
    only a released build can contradict it. A development build is expected
    to carry unreleased work, and the endpoint answering there says nothing
    either way - which is why that case is skipped rather than asserted.
    """
    from busylib import exceptions

    metadata = bar.method_compatibility("access_tokens_list")
    assert metadata is not None

    firmware = bar.status().firmware
    branch = (firmware.branch if firmware else None) or ""
    on_release = bool(re.fullmatch(r"\d+\.\d+\.\d+", branch))

    try:
        bar.access_tokens_list()
    except exceptions.BusyBarAPIError as exc:
        assert metadata.get("status") == "experimental", (
            f"endpoint failed ({exc}) but is not marked experimental"
        )
    else:
        if not on_release:
            pytest.skip(
                f"firmware branch {branch!r} is not a release, so an "
                "unreleased endpoint working here proves nothing"
            )
        assert metadata.get("status") != "experimental", (
            "endpoint works on released firmware but is still marked "
            "experimental - the marker should be a version floor now"
        )
