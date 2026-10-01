"""
The manager's one conversation with a bar.

Everything that calls the device is here, so the interface above it deals in
plain results and `ManagerError`s with a sentence worth showing, and a test
can replace this one class with a table.
"""

from __future__ import annotations

from typing import Protocol

from busylib import exceptions, types

from .model import ManagerError


class AppsClient(Protocol):
    """
    The parts of `AsyncBusyBar` this uses.
    """

    async def apps_list(self) -> types.AppListResult: ...
    async def apps_stage(self, package: bytes) -> types.AppStageResult: ...
    async def apps_install(self, install_key: int) -> types.SuccessResponse: ...
    async def apps_launch(self, app_id: str) -> types.SuccessResponse: ...
    async def apps_quit(self) -> types.SuccessResponse: ...
    async def apps_delete(self, app_id: str) -> types.SuccessResponse: ...


NO_APPS_YET = (
    "This bar's firmware has no JavaScript apps yet. They are on development "
    "firmware from September 2026; update the bar to use them."
)


class Bar:
    """
    A bar, as far as applications go.
    """

    def __init__(self, client: AppsClient, address: str = "") -> None:
        self.client = client
        self.address = address

    async def installed(self) -> list[types.AppInfo]:
        try:
            return (await self.client.apps_list()).apps
        except exceptions.BusyBarAPIError as err:
            if err.status_code == 404:
                raise ManagerError(NO_APPS_YET) from err
            raise self._explain(err, "listing apps") from err
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err

    async def stage(self, package: bytes) -> types.AppStageResult:
        """
        Hand the bar a package. Nothing changes on it until `install`.
        """
        try:
            return await self.client.apps_stage(package)
        except exceptions.BusyBarAPIError as err:
            if err.status_code == 413:
                raise ManagerError("the bar says the package is too large") from err
            if err.status_code == 404:
                raise ManagerError(NO_APPS_YET) from err
            if err.status_code == 400:
                raise ManagerError(
                    "the bar did not accept the package: it is not an application "
                    "it can load"
                ) from err
            raise self._explain(err, "staging the package") from err
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err

    async def install(self, staged: types.AppStageResult) -> None:
        try:
            await self.client.apps_install(staged.install_key)
        except exceptions.BusyBarAPIError as err:
            if err.status_code == 400:
                # The key is single use and belongs to one staging; staging
                # again, from here or from another tool, replaces it.
                raise ManagerError(
                    "the bar no longer has this package staged (something else "
                    "uploaded one in between); try again"
                ) from err
            raise self._explain(err, "installing") from err
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err

    async def launch(self, app_id: str) -> None:
        try:
            await self.client.apps_launch(app_id)
        except exceptions.BusyBarAPIError as err:
            if err.status_code == 404:
                raise ManagerError(
                    f"the bar cannot launch {app_id}: it is not installed, or "
                    "this firmware predates launching from outside (FW-1188)"
                ) from err
            raise self._explain(err, f"launching {app_id}") from err
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err

    async def quit(self) -> None:
        try:
            await self.client.apps_quit()
        except exceptions.BusyBarAPIError as err:
            if err.status_code == 409:
                raise ManagerError("no app is running on the bar") from err
            if err.status_code == 404:
                raise ManagerError(
                    "this firmware cannot quit an app from outside (FW-1189)"
                ) from err
            raise self._explain(err, "quitting the app") from err
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err

    async def delete(self, app_id: str) -> None:
        try:
            await self.client.apps_delete(app_id)
        except exceptions.BusyBarAPIError as err:
            if err.status_code == 404:
                raise ManagerError(f"{app_id} is not on the bar any more") from err
            raise self._explain(err, f"removing {app_id}") from err
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err

    # Messages ----------------------------------------------------------

    def _unreachable(self, err: exceptions.BusyBarError) -> ManagerError:
        where = f" at {self.address}" if self.address else ""
        return ManagerError(f"the bar{where} did not answer ({err})")

    @staticmethod
    def _explain(err: exceptions.BusyBarAPIError, doing: str) -> ManagerError:
        if err.status_code == 403:
            return ManagerError(
                f"the bar refused {doing}: it needs its access key (--token)"
            )
        if err.status_code == 409:
            return ManagerError(f"the bar is busy and refused {doing}; try again")
        return ManagerError(f"the bar refused {doing} ({err.status_code}: {err.error})")


def replacing(staged: types.AppStageResult) -> str:
    """
    What installing a staged package will do, in a sentence.
    """
    new = staged.staged
    old = staged.installed
    if old is None:
        return f"Install {new.name} {new.version}."
    if old.version == new.version:
        return f"Reinstall {new.name} {new.version} (already on the bar)."
    return f"Replace {old.name} {old.version} with {new.version}."
