from __future__ import annotations

import asyncio

import httpx2
import pytest

from busylib import AsyncBusyBar, exceptions, types
from examples.manager.bar import Bar, CannotQuitDirectly, replacing
from examples.manager.model import ManagerError


def _app(**overrides: object) -> dict[str, object]:
    return {"id": "demo.app", "name": "Demo", "version": "1.0.0"} | overrides


class _Firmware:
    """
    A bar that answers from a table, with the real client in front of it so
    that what is tested is the translation of real errors.
    """

    def __init__(self, answers: dict[tuple[str, str], tuple[int, object]]) -> None:
        self.answers = answers
        self.seen: list[httpx2.Request] = []

    async def _handle(self, request: httpx2.Request) -> httpx2.Response:
        self.seen.append(request)
        status, body = self.answers.get(
            (request.method, request.url.path), (404, {"error": "Not Found"})
        )
        return httpx2.Response(status, json=body)

    def bar(self) -> Bar:
        client = AsyncBusyBar(
            addr="http://device.local", transport=httpx2.MockTransport(self._handle)
        )
        return Bar(client, "device.local")


@pytest.mark.asyncio
async def test_what_is_installed_is_what_the_bar_lists() -> None:
    firmware = _Firmware(
        {("GET", "/api/apps/list"): (200, {"apps": [_app(), _app(id="b", name="B")]})}
    )

    apps = await firmware.bar().installed()

    assert [app.id for app in apps] == ["demo.app", "b"]


@pytest.mark.asyncio
async def test_a_bar_without_apps_says_it_needs_newer_firmware() -> None:
    with pytest.raises(ManagerError, match="no JavaScript apps yet"):
        await _Firmware({}).bar().installed()


@pytest.mark.asyncio
async def test_an_unreachable_bar_is_reported_with_its_address() -> None:
    async def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("no route to host")

    client = AsyncBusyBar(
        addr="http://device.local", transport=httpx2.MockTransport(refuse)
    )

    with pytest.raises(ManagerError, match="at device.local did not answer"):
        await Bar(client, "device.local").installed()


@pytest.mark.asyncio
async def test_a_bar_that_wants_its_key_says_so() -> None:
    firmware = _Firmware({("GET", "/api/apps/list"): (403, {"error": "Forbidden"})})

    with pytest.raises(ManagerError, match="needs its access key"):
        await firmware.bar().installed()


@pytest.mark.asyncio
async def test_staging_then_installing_uses_the_key_staging_returned() -> None:
    firmware = _Firmware(
        {
            ("POST", "/api/apps/stage"): (
                200,
                {"result": "OK", "install_key": 777, "staged": _app()},
            ),
            ("POST", "/api/apps/install"): (200, {"result": "OK"}),
        }
    )
    bar = firmware.bar()

    staged = await bar.stage(b"package")
    await bar.install(staged)

    assert dict(firmware.seen[1].url.params) == {"install_key": "777"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status, complaint",
    [
        (413, "too large"),
        (400, "not an application it can load"),
        (404, "no JavaScript apps yet"),
    ],
)
async def test_a_refused_package_says_why(status: int, complaint: str) -> None:
    firmware = _Firmware({("POST", "/api/apps/stage"): (status, {"error": "x"})})

    with pytest.raises(ManagerError, match=complaint):
        await firmware.bar().stage(b"package")


@pytest.mark.asyncio
async def test_a_stale_install_key_is_explained_not_reported_as_a_bad_request() -> None:
    firmware = _Firmware(
        {("POST", "/api/apps/install"): (400, {"error": "Bad Request"})}
    )
    staged = types.AppStageResult(
        result="OK", install_key=1, staged=types.AppInfo(id="a", name="A", version="1")
    )

    with pytest.raises(ManagerError, match="no longer has this package staged"):
        await firmware.bar().install(staged)


@pytest.mark.asyncio
async def test_quitting_with_nothing_running_is_not_a_crash() -> None:
    firmware = _Firmware({("POST", "/api/apps/quit"): (409, {"error": "not running"})})

    with pytest.raises(ManagerError, match="no app is running"):
        await firmware.bar().quit()


@pytest.mark.asyncio
async def test_launching_on_firmware_without_it_points_at_the_firmware() -> None:
    with pytest.raises(ManagerError, match="predates launching from outside"):
        await _Firmware({}).bar().launch("demo.app")


@pytest.mark.asyncio
async def test_deleting_what_is_already_gone_says_so() -> None:
    with pytest.raises(ManagerError, match="not on the bar any more"):
        await (
            _Firmware({("DELETE", "/api/apps"): (404, {"error": "x"})})
            .bar()
            .delete("a")
        )


@pytest.mark.parametrize(
    "installed, expected",
    [
        (None, "Install Demo 2.0.0."),
        ("1.0.0", "Replace Demo 1.0.0 with 2.0.0."),
        ("2.0.0", "Reinstall Demo 2.0.0 (already on the bar)."),
    ],
)
def test_what_installing_will_do_is_said_before_it_is_done(
    installed: str | None, expected: str
) -> None:
    staged = types.AppStageResult(
        result="OK",
        install_key=1,
        staged=types.AppInfo(id="demo.app", name="Demo", version="2.0.0"),
        installed=(
            types.AppInfo(id="demo.app", name="Demo", version=installed)
            if installed
            else None
        ),
    )

    assert replacing(staged) == expected


# Whether the bar is there ---------------------------------------------------------


def _bar_of(client: object, address: str = "") -> Bar:
    # The fake scripts only the two calls the connection makes; the rest of the
    # client's surface is not what these tests are about.
    return Bar(client, address)  # type: ignore[arg-type]


class _Client:
    """
    The two calls the connection needs, scripted.
    """

    def __init__(self, version=None, stream=None) -> None:
        self._version = version
        self._stream = stream

    async def version(self):
        if isinstance(self._version, Exception):
            raise self._version
        if self._version == "hang":
            await asyncio.sleep(30)
        return types.VersionInfo(api_semver=self._version)

    async def stream_status_ws(self, **_):
        for item in self._stream or []:
            if isinstance(item, Exception):
                raise item
            yield item


async def test_the_version_is_what_the_bar_reports() -> None:
    assert await _bar_of(_Client("27.9.0")).version() == "27.9.0"


async def test_a_bar_that_does_not_answer_a_question_is_known_to_be_gone_quickly() -> (
    None
):
    """
    The client retries a failed request, which suits a command and not a
    question asked every few seconds.
    """
    with pytest.raises(ManagerError, match="no answer in 0.05 s"):
        await _bar_of(_Client("hang")).version(timeout=0.05)


async def test_a_bar_that_refuses_the_question_says_where_it_was() -> None:
    client = _Client(
        exceptions.BusyBarRequestError("refused", method="GET", path="/api/version")
    )

    with pytest.raises(ManagerError, match="at 10.0.4.20 did not answer"):
        await _bar_of(client, "10.0.4.20").version()


async def test_holding_returns_when_the_socket_closes() -> None:
    await _bar_of(_Client(stream=[b"a", b"b"])).hold()


async def test_holding_says_how_the_socket_broke() -> None:
    client = _Client(
        stream=[b"a", exceptions.BusyBarWebSocketError("closed", path="/api/status/ws")]
    )

    with pytest.raises(ManagerError, match="did not answer"):
        await _bar_of(client, "10.0.4.20").hold()


async def test_a_socket_that_could_not_be_opened_is_the_same_kind_of_answer() -> None:
    client = _Client(stream=[OSError("connection refused")])

    with pytest.raises(ManagerError, match="the connection broke"):
        await _bar_of(client).hold()


# Getting out of the running app ---------------------------------------------------


@pytest.mark.parametrize(
    "status, complaint",
    [
        (404, "firmware has no way to quit an app"),
        (503, "tried to quit the app and could not"),
    ],
)
async def test_a_bar_that_cannot_be_asked_to_quit_says_there_is_another_way(
    status: int, complaint: str
) -> None:
    firmware = _Firmware({("POST", "/api/apps/quit"): (status, {"error": "x"})})

    with pytest.raises(CannotQuitDirectly, match=complaint):
        await firmware.bar().quit()


async def test_no_app_running_is_not_a_reason_to_move_the_switch() -> None:
    """
    409 is the one honest answer the bar gives, and moving the switch would be
    a heavy-handed reply to "there is nothing to stop".
    """
    firmware = _Firmware({("POST", "/api/apps/quit"): (409, {"error": "x"})})

    with pytest.raises(ManagerError, match="no app is running") as raised:
        await firmware.bar().quit()

    assert not isinstance(raised.value, CannotQuitDirectly)


async def test_leaving_by_the_switch_goes_back_then_off_then_apps() -> None:
    """
    The bar ignores a move to the position it believes it is at, and which that
    is cannot be known - so the move is to Off and then back to Apps, and one
    of the two is always a real change.
    """
    firmware = _Firmware({("POST", "/api/input"): (200, {"result": "OK"})})
    pauses: list[float] = []

    async def sleep(seconds: float) -> None:
        pauses.append(seconds)

    await firmware.bar().leave_by_switch(pause=1.5, sleep=sleep)

    assert [r.url.params["key"] for r in firmware.seen] == ["back", "off", "apps"]
    assert pauses == [1.5, 1.5], "each change gets time to take effect before the next"


async def test_leaving_by_the_switch_stops_if_the_bar_goes_away_midway() -> None:
    firmware = _Firmware({})  # every request is a 404

    async def sleep(seconds: float) -> None:
        pass

    with pytest.raises(ManagerError):
        await firmware.bar().leave_by_switch(sleep=sleep)

    assert len(firmware.seen) == 1, "no further presses after one has failed"


# Sharing the socket ---------------------------------------------------------------


@pytest.mark.asyncio
async def test_what_the_socket_receives_is_handed_to_whoever_listens() -> None:
    bar = _bar_of(_Client(stream=[{"updates": [1]}, b"raw", "text", {"updates": [2]}]))
    heard: list[dict] = []
    stop = bar.listen(heard.append)

    await bar.hold()
    stop()
    await _bar_of(_Client(stream=[{"updates": [3]}])).hold()

    # Only the decoded messages; and nothing after listening stopped.
    assert heard == [{"updates": [1]}, {"updates": [2]}]


@pytest.mark.asyncio
async def test_a_message_the_bar_sends_that_cannot_be_read_is_not_a_lost_bar() -> None:
    bar = _bar_of(
        _Client(
            stream=[
                exceptions.BusyBarProtocolError(
                    "bad", method="GET", path="/api/status/ws"
                )
            ]
        )
    )

    with pytest.raises(ManagerError, match="unreadable"):
        await bar.hold()


@pytest.mark.asyncio
async def test_a_key_is_pressed_as_a_hand_would() -> None:
    firmware = _Firmware({("POST", "/api/input"): (200, {"result": "OK"})})

    await firmware.bar().press(types.InputKey.OK)

    request = firmware.seen[0]
    assert (request.method, request.url.path) == ("POST", "/api/input")
    assert request.url.params["key"] == "ok"


@pytest.mark.asyncio
async def test_a_refused_key_says_why() -> None:
    firmware = _Firmware({("POST", "/api/input"): (403, {"error": "Forbidden"})})

    with pytest.raises(ManagerError, match="needs its access key"):
        await firmware.bar().press(types.InputKey.OK)


@pytest.mark.asyncio
async def test_a_display_that_cannot_be_read_is_just_no_picture() -> None:
    assert await _Firmware({}).bar().front_screen() is None


# The bar's log --------------------------------------------------------------------


class _Logs:
    """
    The three calls a log dump makes, scripted and recorded.
    """

    def __init__(
        self,
        *,
        dump: object = None,
        read: bytes | Exception = b"log text",
        remove: Exception | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._dump, self._read, self._remove = dump, read, remove

    async def log_dump(self, filename=None, *, path=None):
        self.calls.append(f"dump filename={filename} path={path}")
        outcomes = self._dump if isinstance(self._dump, list) else [self._dump]
        outcome = outcomes[min(len(self.calls) - 1, len(outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return types.LogDumpResponse(result="OK", path=path or f"/ext/{filename}.txt")

    async def storage_read(self, path):
        self.calls.append(f"read {path}")
        if isinstance(self._read, Exception):
            raise self._read
        return self._read

    async def storage_remove(self, path):
        self.calls.append(f"remove {path}")
        if isinstance(self._remove, Exception):
            raise self._remove
        return types.SuccessResponse(result="OK")


def _api_error(status: int) -> exceptions.BusyBarAPIError:
    return exceptions.BusyBarAPIError("no", status_code=status)


@pytest.mark.asyncio
async def test_the_log_is_dumped_read_and_the_file_removed_again() -> None:
    client = _Logs(read=b"line one\r\nline two")

    data = await _bar_of(client).fetch_log()

    assert data == b"line one\r\nline two"
    assert client.calls == [
        "dump filename=busy_apps_manager path=None",
        "read /ext/busy_apps_manager.txt",
        "remove /ext/busy_apps_manager.txt",
    ]


@pytest.mark.asyncio
async def test_firmware_before_the_name_form_is_asked_for_a_path() -> None:
    client = _Logs(dump=[_api_error(400), None])

    await _bar_of(client).fetch_log()

    assert client.calls[:2] == [
        "dump filename=busy_apps_manager path=None",
        "dump filename=None path=/ext/busy_apps_manager.txt",
    ]


@pytest.mark.asyncio
async def test_a_file_that_cannot_be_removed_does_not_cost_the_log() -> None:
    client = _Logs(remove=exceptions.BusyBarError("busy"))

    assert await _bar_of(client).fetch_log() == b"log text"


@pytest.mark.asyncio
async def test_a_bar_that_wants_its_key_says_so_for_the_log_too() -> None:
    with pytest.raises(ManagerError, match="needs its access key"):
        await _bar_of(_Logs(dump=_api_error(403))).fetch_log()


@pytest.mark.asyncio
async def test_a_bar_that_goes_while_the_log_is_read_is_said_to_be_gone() -> None:
    client = _Logs(read=exceptions.BusyBarError("reset"))

    with pytest.raises(ManagerError, match="did not answer"):
        await _bar_of(client, "10.0.4.20").fetch_log()
    assert not any(call.startswith("remove") for call in client.calls)
