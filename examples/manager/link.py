"""
Whether the bar is there, and telling someone when that changes.

A manager that is open for an hour will see the bar go and come back - it
reboots after a firmware update, its network drops, a cable moves - and a list
that goes stale without a word is worse than one that says it has lost the bar.
This keeps a connection and reports the two moments that matter: it went, and
it is back.

Nothing here knows about a terminal. The interface hands it a function to call.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from .model import ManagerError

# How long to wait before asking again, growing while the bar stays away and
# never past the last: a bar that is rebooting should be noticed within
# seconds of coming back, and one that is gone should not be hammered.
RETRY: tuple[float, ...] = (1.0, 2.0, 4.0, 8.0, 15.0)

# How often to ask when there is no socket to wait on.
POLL = 5.0


class Watched(Protocol):
    async def version(self) -> str: ...

    async def hold(self) -> None: ...


@dataclass(frozen=True)
class Up:
    """
    The bar answered.

    `previous` is the API version it reported last time, so a firmware update
    is visible as a changed number. `after` is how many seconds it was gone,
    or None for the first time it was reached.
    """

    api: str
    previous: str = ""
    after: float | None = None


@dataclass(frozen=True)
class Down:
    """
    The bar stopped answering. `first` means it never answered at all, which
    is a different sentence from losing a bar that was there.
    """

    reason: str
    first: bool = False


Event = Up | Down
Report = Callable[[Event], None]


async def watch(
    bar: Watched,
    report: Report,
    *,
    retry: Sequence[float] = RETRY,
    poll: float = POLL,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    now: Callable[[], float] = time.monotonic,
) -> None:
    """
    Report when the bar goes and when it comes back, for as long as it runs.

    Each round asks the bar its version - that is the answer to "is it there"
    - and, if it is, holds a socket open to it, which closes the instant the
    bar goes. A closed socket is checked against a fresh question before it is
    called a loss, because a socket can fail for its own reasons (a firmware
    without the endpoint, a proxy that does not pass them) while the bar is
    perfectly well; then the watch falls back to asking every few seconds,
    quietly, until the bar really does stop answering.
    """
    api = ""
    down_since: float | None = None
    announced = False
    attempt = 0
    socket_works = True

    while True:
        try:
            version = await bar.version()
        except ManagerError as err:
            if not announced:
                report(Down(str(err), first=api == ""))
                announced = True
                down_since = now()
            await sleep(retry[min(attempt, len(retry) - 1)])
            attempt += 1
            continue

        report(
            Up(
                api=version,
                previous=api,
                after=None if down_since is None else now() - down_since,
            )
        )
        api, down_since, announced, attempt = version, None, False, 0
        socket_works = True

        # Present. Wait here for as long as it stays so.
        while True:
            if socket_works:
                try:
                    await bar.hold()
                    reason = "the connection closed"
                except ManagerError as err:
                    reason = str(err)
                try:
                    await bar.version()
                except ManagerError:
                    break
                # It answers, so it was the socket and not the bar.
                socket_works = False
                continue
            await sleep(poll)
            try:
                await bar.version()
            except ManagerError as err:
                reason = str(err)
                break

        down_since = now()
        announced = True
        report(Down(reason))
        await sleep(retry[0])
