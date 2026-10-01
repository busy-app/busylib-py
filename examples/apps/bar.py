"""
The manager's one conversation with a bar.

Everything that calls the device is here, so the interface above it deals in
plain results and `ManagerError`s with a sentence worth showing, and a test
can replace this one class with a table.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Protocol

from busylib import exceptions, types

from .model import ManagerError


class CannotQuitDirectly(ManagerError):
    """
    The bar could not be asked to quit the app: its firmware has no way to,
    or it tried and did not manage.

    Not an error to show and forget. There is another way, and it changes what
    the bar is showing, so the person is asked before it is used.
    """


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
    async def input(self, key: types.InputKey) -> types.SuccessResponse: ...
    async def version(self) -> types.VersionInfo: ...
    def stream_status_ws(self) -> AsyncIterator[Any]: ...


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
        """
        Ask the bar to stop the running app, which it does gracefully: the
        script is told to end and given the chance, then stopped.

        The bar cannot say which app is running, and this is the one honest
        answer there is - a 409 means none is.
        """
        try:
            await self.client.apps_quit()
        except exceptions.BusyBarAPIError as err:
            if err.status_code == 409:
                raise ManagerError("no app is running on the bar") from err
            if err.status_code in (404, 503):
                raise CannotQuitDirectly(
                    "this bar's firmware has no way to quit an app"
                    if err.status_code == 404
                    else "the bar tried to quit the app and could not"
                ) from err
            raise self._explain(err, "quitting the app") from err
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err

    async def leave_by_switch(
        self,
        pause: float = 1.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        """
        Get out of the running app the way a hand would, when the bar cannot
        be asked to quit it.

        Back first. The launcher swallows Back while a script runs, so this
        helps only a script that handles it itself, but it costs nothing.
        Then the switch: moving it replaces whatever is running with the app
        for that position, which stops the script. The bar ignores a move to
        the position it already thinks it is at, and which that is cannot be
        known, so the move goes to Off and then back to Apps: whichever the
        bar was at, one of the two is a real change, and it ends in the Apps
        menu, which is where quitting an app leads anyway.

        Off is the gentle place to go through. Its app plays the switching-off
        animation and lets the displays sleep, and leaves the network alone, so
        the move back arrives; Settings and Busy would start an app of their
        own for a moment.

        The pause lets each change take effect before the next one: the app
        has to be stopped, and joined, before it is replaced again.
        """
        try:
            for step, key in enumerate(
                (types.InputKey.BACK, types.InputKey.OFF, types.InputKey.APPS)
            ):
                if step:
                    await sleep(pause)
                await self.client.input(key)
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

    # The connection ----------------------------------------------------

    async def version(self, timeout: float = 4.0) -> str:
        """
        The API version the bar reports, which is also the quickest honest
        answer to "is it there".

        The client retries a failed request, which is right for a command and
        wrong for a question asked every few seconds: a bar that has gone
        should be known to have gone in `timeout` seconds, not after every
        retry has had its turn.
        """
        try:
            info = await asyncio.wait_for(self.client.version(), timeout)
        except asyncio.TimeoutError as err:
            raise ManagerError(f"no answer in {timeout:g} s") from err
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err
        return info.api_semver or ""

    async def hold(self) -> None:
        """
        Keep a WebSocket to the bar open, and return when it closes.

        A socket is the quickest way to learn a bar has gone: when it reboots
        or its network drops, the connection closes at once, where polling
        would find out at the next poll. Its keepalive pings catch the bar
        that vanishes without saying so, within about forty seconds.

        What arrives on it is not used here; the manager only needs to know
        whether it is still there. Raises `ManagerError` if the socket could
        not be opened or broke, and returns if it was closed cleanly.
        """
        try:
            async for _ in self.client.stream_status_ws(decode_protobuf=False):
                pass
        except exceptions.BusyBarError as err:
            raise self._unreachable(err) from err
        except OSError as err:
            raise ManagerError(f"the connection broke ({err})") from err

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
