from __future__ import annotations

import httpx2
import pytest

from busylib import AsyncBusyBar, types
from examples.apps.bar import Bar, replacing
from examples.apps.model import ManagerError


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
