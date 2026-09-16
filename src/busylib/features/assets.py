"""
What a particular bar can draw and play.

Assets are files, which means no list written down anywhere is true of a
given bar: the firmware ships one set, a release adds to it, and an owner
uploads their own or deletes what they do not want. So anything that
offers a choice - an icon picker, a sound dropdown, a theme list - has to
ask the bar, and this is how.

Both places are read: what the firmware shipped, under `/ext/apps_assets`,
and what applications uploaded, under `/ext/assets`. An uploaded file is
addressed by its full path and a shipped one by the short form drawings
use, and both are returned ready to pass straight to a draw or a play
call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .. import exceptions, types

# Where the firmware's own assets live, and where uploads land. The
# second is the firmware's `ASSETS_UPLOAD_DIR`, and it is also what the
# display and audio endpoints resolve a `path` against - relative to the
# uploading application's own folder inside it.
ASSETS_ROOT = "/ext/apps_assets"
UPLOADS_ROOT = "/ext/user_assets"

AssetKind = Literal["image", "animation", "sound", "font", "theme"]

# What the device calls each kind of file. A theme is a directory with a
# theme.json in it rather than a file, and is handled separately.
_EXTENSIONS: dict[str, AssetKind] = {
    ".image": "image",
    ".anim": "animation",
    ".snd": "sound",
    ".font": "font",
}

# What an upload may be. The firmware decodes these itself, which is why
# an uploaded icon is a PNG where a shipped one is an `.image`.
_UPLOAD_EXTENSIONS: dict[str, AssetKind] = {
    ".png": "image",
    ".image": "image",
    ".anim": "animation",
    ".snd": "sound",
    ".wav": "sound",
}

# The folders the firmware ships, in the order a reader would expect them:
# shared things first, then the timer's own.
_SHIPPED = (
    "shared/images",
    "shared/animations",
    "shared/sounds",
    "shared/fonts",
    "busy/images",
    "busy/animations",
    "busy/sounds",
)

_THEMES = "busy/themes"


@dataclass(frozen=True)
class Asset:
    """
    One file on a bar, and how to name it in a call.

    `reference` is what you pass, and which field it goes in depends on
    where the file came from. A shipped asset is named by `stock_path`
    and carries its folder: `shared/images/clock_5x5.image`. An upload is
    named by `path` and is just the file name, because the device
    resolves it inside the uploading application's own folder - so the
    same name in two applications is two different files, and
    `application` says which one this is.
    """

    name: str
    reference: str
    kind: AssetKind
    application: str | None = None

    @property
    def is_upload(self) -> bool:
        """
        Whether this is something an application put there.
        """
        return self.application is not None

    @property
    def device_path(self) -> str:
        """
        Where the file actually is, for reading it back.
        """
        if self.application is None:
            return f"{ASSETS_ROOT}/{self.reference}"
        return f"{UPLOADS_ROOT}/{self.application}/{self.reference}"


class AssetCatalogueClient(Protocol):
    """
    What discovery needs, which is one listing call.
    """

    async def storage_list(self, path: str) -> types.StorageList: ...


async def _entries(
    client: AssetCatalogueClient, path: str
) -> list[types.StorageListElement]:
    """
    List one directory, treating a missing one as empty.

    A bar that has never had an upload has no `/ext/assets` at all, and a
    firmware without the timer has no `busy/` folders - neither is an
    error for a catalogue, which is meant to describe what is there.
    """
    try:
        listing = await client.storage_list(path)
    except exceptions.BusyBarError:
        return []
    return list(listing.list or [])


def _shipped(directory: str, name: str) -> Asset | None:
    """
    Turn a firmware file into an asset, or None if it is not one.
    """
    for extension, kind in _EXTENSIONS.items():
        if name.endswith(extension):
            return Asset(
                name=name.removesuffix(extension),
                reference=f"{directory}/{name}",
                kind=kind,
            )
    return None


def _uploaded(application: str, relative: str) -> Asset | None:
    """
    Turn an uploaded file into an asset, or None if it is not one.
    """
    for extension, kind in _UPLOAD_EXTENSIONS.items():
        if relative.endswith(extension):
            return Asset(
                name=relative.removesuffix(extension),
                reference=relative,
                kind=kind,
                application=application,
            )
    return None


async def discover_assets(client: AssetCatalogueClient) -> list[Asset]:
    """
    Every asset this bar holds: shipped, and uploaded by applications.

    Ordered by kind and then by name, so a list offered to a person is
    stable between calls and between bars.

    This is a listing, not a read: nothing here opens a file, so an
    image's width - which a layout needs and a file name does not always
    carry - is read later, by `notification.icon_at`, for the one asset
    that ends up being used.
    """
    found: list[Asset] = []

    for directory in _SHIPPED:
        for entry in await _entries(client, f"{ASSETS_ROOT}/{directory}"):
            if entry.type != "file" or not entry.name:
                continue
            asset = _shipped(directory, entry.name)
            if asset is not None:
                found.append(asset)

    for entry in await _entries(client, f"{ASSETS_ROOT}/{_THEMES}"):
        if entry.type == "dir" and entry.name:
            found.append(
                Asset(
                    name=entry.name,
                    reference=f"{_THEMES}/{entry.name}",
                    kind="theme",
                )
            )

    # Uploads are one directory per application, and an application may
    # have made sub-directories of its own inside it. The reference stays
    # relative to the application's folder, since that is what the device
    # joins a `path` onto.
    for application in await _entries(client, UPLOADS_ROOT):
        if application.type != "dir" or not application.name:
            continue
        pending = [""]
        while pending:
            relative = pending.pop()
            directory = f"{UPLOADS_ROOT}/{application.name}"
            if relative:
                directory = f"{directory}/{relative}"
            for entry in await _entries(client, directory):
                if not entry.name:
                    continue
                child = f"{relative}/{entry.name}" if relative else entry.name
                if entry.type == "dir":
                    pending.append(child)
                    continue
                asset = _uploaded(application.name, child)
                if asset is not None:
                    found.append(asset)

    order: dict[AssetKind, int] = {
        "image": 0,
        "animation": 1,
        "sound": 2,
        "font": 3,
        "theme": 4,
    }
    return sorted(found, key=lambda asset: (order[asset.kind], asset.name))


async def of_kind(client: AssetCatalogueClient, kind: AssetKind) -> dict[str, str]:
    """
    One kind of asset, as the name-to-path mapping a picker wants.

    A name collision between a shipped asset and an uploaded one - two
    files called `logo` - resolves to the upload, because that is the one
    its owner put there on purpose.
    """
    wanted = [asset for asset in await discover_assets(client) if asset.kind == kind]
    catalogue = {asset.name: asset.reference for asset in wanted if not asset.is_upload}
    catalogue.update(
        {asset.name: asset.reference for asset in wanted if asset.is_upload}
    )
    return dict(sorted(catalogue.items()))
