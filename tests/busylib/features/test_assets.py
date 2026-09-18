"""
Copying an upload from one application's folder to another's.
"""

from __future__ import annotations

from busylib import types
from busylib.features import assets


class FakeBar:
    """
    A bar with one upload, belonging to somebody else.
    """

    def __init__(self) -> None:
        self.uploaded: list[tuple[str, str, bytes]] = []

    async def storage_list(self, path: str) -> types.StorageList:
        if path == assets.UPLOADS_ROOT:
            return types.StorageList(
                list=[types.StorageDirElement(type="dir", name="draw_tool")]
            )
        if path == f"{assets.UPLOADS_ROOT}/draw_tool":
            return types.StorageList(
                list=[types.StorageFileElement(type="file", name="logo.png", size=80)]
            )
        return types.StorageList(list=[])

    async def storage_read(self, path: str) -> bytes:
        assert path == f"{assets.UPLOADS_ROOT}/draw_tool/logo.png"
        return b"a picture, already converted for the panel"

    async def assets_upload(
        self, application_name: str, filename: str, data: bytes
    ) -> types.SuccessResponse:
        self.uploaded.append((application_name, filename, data))
        return types.SuccessResponse(result="OK")


async def test_an_upload_can_be_taken_over_by_another_application() -> None:
    """
    The device resolves a name inside the drawing application's own
    folder, so a picture uploaded by the Draw Tool cannot be drawn by
    anyone else until it is copied across.
    """
    bar = FakeBar()
    theirs = next(
        asset
        for asset in await assets.discover_assets(bar)
        if asset.application == "draw_tool"
    )

    ours = await assets.copy_to_application(bar, theirs, "home_assistant")

    assert ours.application == "home_assistant"
    assert ours.name == "logo"
    application, filename, data = bar.uploaded[0]
    assert (application, filename) == ("home_assistant", "logo.png")
    # Byte for byte: it was converted for the device when it was first
    # uploaded, and converting it again would be a second guess.
    assert data == b"a picture, already converted for the panel"


async def test_copying_something_already_ours_asks_the_bar_for_nothing() -> None:
    bar = FakeBar()
    mine = assets.Asset(
        name="logo", reference="logo.png", kind="image", application="home_assistant"
    )

    assert await assets.copy_to_application(bar, mine, "home_assistant") is mine
    assert not bar.uploaded
