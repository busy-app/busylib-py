from __future__ import annotations

import json

import httpx2
import pytest

from busylib import AsyncBusyBar, BusyBar, exceptions, types


def _app(**overrides: object) -> dict[str, object]:
    """
    One application as the bar describes it.
    """
    return {
        "id": "taro.knock_roll",
        "name": "Knock Roll Die",
        "version": "1.0.0",
        "author": "Somebody",
        "description": "Tarot, magic 8 ball and dice",
        "icon_path": "/ext/apps_assets/shared/images/unknown_app_front_8x8.image",
        "is_debug": False,
    } | overrides


class _Bar:
    """
    A bar that records what it was asked and answers from a table.

    Responses are built per request: one can only be read once, and an
    async transport wants an async handler, which is why there are two.
    """

    def __init__(self, answers: dict[tuple[str, str], tuple[int, object]]) -> None:
        self.answers = answers
        self.seen: list[httpx2.Request] = []

    def _answer(self, request: httpx2.Request) -> httpx2.Response:
        self.seen.append(request)
        status, body = self.answers.get(
            (request.method, request.url.path), (404, {"error": "no such route"})
        )
        return httpx2.Response(status, json=body)

    def client(self) -> BusyBar:
        return BusyBar(
            addr="http://device.local", transport=httpx2.MockTransport(self._answer)
        )

    def async_client(self) -> AsyncBusyBar:
        async def handler(request: httpx2.Request) -> httpx2.Response:
            return self._answer(request)

        return AsyncBusyBar(
            addr="http://device.local", transport=httpx2.MockTransport(handler)
        )


OK = (200, {"result": "OK"})


def test_the_list_says_what_is_installed() -> None:
    bar = _Bar(
        {
            ("GET", "/api/apps/list"): (
                200,
                {"apps": [_app(), _app(id="weather", name="Weather")]},
            )
        }
    )

    apps = bar.client().apps_list().apps

    assert [app.id for app in apps] == ["taro.knock_roll", "weather"]
    assert apps[0].version == "1.0.0"


def test_an_app_the_bar_describes_thinly_still_reads() -> None:
    """
    Author, description and icon are optional in practice: a package that
    leaves them out should list, not fail the whole listing.
    """
    bar = _Bar(
        {
            ("GET", "/api/apps/list"): (
                200,
                {"apps": [{"id": "a", "name": "A", "version": "0.1"}]},
            )
        }
    )

    (app,) = bar.client().apps_list().apps

    assert (app.author, app.description, app.is_debug) == ("", "", False)


def test_staging_sends_the_package_whole_with_its_length() -> None:
    """
    The bar answers 400 to a body of unknown length, so the package goes
    as one piece and not as a stream.
    """
    bar = _Bar(
        {
            ("POST", "/api/apps/stage"): (
                200,
                {
                    "result": "OK",
                    "install_key": 123456789,
                    "staged": _app(version="1.1.0"),
                    "installed": _app(),
                },
            )
        }
    )

    staged = bar.client().apps_stage(b"the package")

    (request,) = bar.seen
    assert request.content == b"the package"
    assert request.headers["content-length"] == str(len(b"the package"))
    assert request.headers["content-type"] == "application/octet-stream"
    assert staged.install_key == 123456789
    assert staged.staged.version == "1.1.0"
    assert staged.installed is not None and staged.installed.version == "1.0.0"


def test_staging_a_new_app_has_nothing_it_replaces() -> None:
    bar = _Bar(
        {
            ("POST", "/api/apps/stage"): (
                200,
                {"result": "OK", "install_key": 7, "staged": _app()},
            )
        }
    )

    assert bar.client().apps_stage(b"x").installed is None


def test_installing_names_the_key_staging_gave() -> None:
    bar = _Bar({("POST", "/api/apps/install"): OK})

    bar.client().apps_install(42)

    assert dict(bar.seen[0].url.params) == {"install_key": "42"}


def test_launching_and_deleting_name_the_app() -> None:
    bar = _Bar(
        {("POST", "/api/apps/launch"): OK, ("DELETE", "/api/apps"): OK},
    )
    client = bar.client()

    client.apps_launch("taro.knock_roll")
    client.apps_delete("taro.knock_roll")

    assert [dict(r.url.params) for r in bar.seen] == [
        {"app_id": "taro.knock_roll"},
        {"app_id": "taro.knock_roll"},
    ]


def test_quitting_when_nothing_runs_is_the_bars_conflict() -> None:
    bar = _Bar(
        {("POST", "/api/apps/quit"): (409, {"error": "Application is not running"})}
    )

    with pytest.raises(exceptions.BusyBarAPIError) as raised:
        bar.client().apps_quit()

    assert raised.value.status_code == 409


def test_settings_travel_as_one_document() -> None:
    bar = _Bar(
        {
            ("GET", "/api/apps/settings"): (
                200,
                {"version": 2, "values": {"volume": 5, "ui": {"big": True}}},
            ),
            ("PUT", "/api/apps/settings"): OK,
            ("DELETE", "/api/apps/settings"): OK,
        }
    )
    client = bar.client()

    document = client.apps_settings("taro.knock_roll")
    client.apps_settings_set(
        "taro.knock_roll",
        types.AppSettingsDocument(version=2, values={"volume": 9}),
    )
    client.apps_settings_reset("taro.knock_roll")

    assert document.values["ui"] == {"big": True}
    assert json.loads(bar.seen[1].content) == {"version": 2, "values": {"volume": 9}}
    assert [r.method for r in bar.seen] == ["GET", "PUT", "DELETE"]


def test_these_calls_say_they_are_not_in_released_firmware() -> None:
    """
    The endpoints exist on development firmware only, and the marker is
    how a caller finds that out without a 404.
    """
    for name in ("apps_list", "apps_stage", "apps_launch", "apps_quit"):
        compatibility = BusyBar(addr="http://device.local").method_compatibility(name)

        assert compatibility is not None
        assert compatibility["status"] == "experimental"


@pytest.mark.asyncio
async def test_async_installs_in_the_same_two_steps() -> None:
    bar = _Bar(
        {
            ("POST", "/api/apps/stage"): (
                200,
                {"result": "OK", "install_key": 9, "staged": _app()},
            ),
            ("POST", "/api/apps/install"): OK,
            ("GET", "/api/apps/list"): (200, {"apps": [_app()]}),
        }
    )

    client = bar.async_client()
    try:
        staged = await client.apps_stage(b"package")
        await client.apps_install(staged.install_key)
        apps = (await client.apps_list()).apps
    finally:
        await client.aclose()

    assert [r.url.path for r in bar.seen] == [
        "/api/apps/stage",
        "/api/apps/install",
        "/api/apps/list",
    ]
    assert apps[0].id == "taro.knock_roll"
