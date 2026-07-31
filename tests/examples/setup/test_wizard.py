from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from busylib import types, versioning
from examples.setup.prompts import SetupCancelled
from examples.setup import steps
from examples.setup.steps import (
    CloudStep,
    FirmwareStep,
    NameStep,
    SetupStep,
    StepStatus,
    TimezoneStep,
    WifiStep,
)
from examples.setup.wizard import collect_status, run_setup


class FakeClient:
    """
    Stands in for AsyncBusyBar, returning canned API responses.
    """

    def __init__(self, **responses: object) -> None:
        self._responses = responses
        self.calls: list[str] = []

    def _get(self, name: str) -> object:
        self.calls.append(name)
        value = self._responses.get(name)
        if isinstance(value, Exception):
            raise value
        return value

    async def version(self):
        return self._get("version")

    async def wifi_status(self):
        return self._get("wifi_status")

    async def time(self):
        return self._get("time")

    async def name(self):
        return self._get("name")

    async def account_info(self):
        return self._get("account_info")


class RecordingPrompt:
    """
    Prompt that records output and replays scripted answers.
    """

    def __init__(self, answers: list[object] | None = None) -> None:
        self.lines: list[str] = []
        self._answers = list(answers or [])

    def info(self, message: str) -> None:
        self.lines.append(message)

    def _next(self) -> object:
        if not self._answers:
            raise SetupCancelled
        return self._answers.pop(0)

    async def text(self, message: str, *, default: str | None = None) -> str:
        return str(self._next())

    async def secret(self, message: str) -> str:
        return str(self._next())

    async def confirm(self, message: str, *, default: bool = True) -> bool:
        return bool(self._next())

    async def choose(self, message: str, options: list[str]) -> int:
        return int(self._next())


def _local_offset_timestamp() -> str:
    """
    Build a timestamp using this machine's own UTC offset.
    """
    return datetime.now().astimezone().isoformat()


@pytest.mark.asyncio
async def test_firmware_step_done_when_api_matches_library() -> None:
    """
    Treat firmware as set up when its API version satisfies the library.
    """
    client = FakeClient(
        version=types.VersionInfo(version="1.1.1", api_semver=versioning.API_VERSION)
    )
    status = await FirmwareStep().status(client)  # type: ignore[arg-type]
    assert status.done is True
    assert versioning.API_VERSION in status.summary


@pytest.mark.asyncio
async def test_firmware_step_pending_on_factory_api_version() -> None:
    """
    Flag a factory bar as needing an update.

    Firmware 1.0.2 ships API 24.3.0 while the library targets 25.0.0, so a
    brand-new bar must land in the pending state.
    """
    client = FakeClient(version=types.VersionInfo(version="1.0.2", api_semver="24.3.0"))
    status = await FirmwareStep().status(client)  # type: ignore[arg-type]
    assert status.done is False
    assert "24.3.0" in status.summary


@pytest.mark.asyncio
async def test_wifi_step_status() -> None:
    """
    Report Wi-Fi as done only when the device is connected.
    """
    connected = FakeClient(
        wifi_status=types.StatusResponse(state=types.WifiState.CONNECTED, ssid="home")
    )
    status = await WifiStep().status(connected)  # type: ignore[arg-type]
    assert status.done is True
    assert status.summary == "home"

    offline = FakeClient(
        wifi_status=types.StatusResponse(state=types.WifiState.DISCONNECTED)
    )
    assert (await WifiStep().status(offline)).done is False  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_timezone_step_done_when_offset_matches_host() -> None:
    """
    Treat the timezone as set when the device offset matches this computer.
    """
    client = FakeClient(
        time=types.DeviceTimeResponse(timestamp=_local_offset_timestamp())
    )
    status = await TimezoneStep().status(client)  # type: ignore[arg-type]
    assert status.done is True
    assert "matches this computer" in status.summary


@pytest.mark.asyncio
async def test_timezone_step_pending_on_unparsable_timestamp() -> None:
    """
    Fall back to pending when the device time can't be interpreted.
    """
    client = FakeClient(time=types.DeviceTimeResponse(timestamp="not-a-timestamp"))
    status = await TimezoneStep().status(client)  # type: ignore[arg-type]
    assert status.done is False


@pytest.mark.asyncio
async def test_name_step_treats_factory_default_as_pending() -> None:
    """
    The stock "BUSY Bar" name counts as not yet configured.
    """
    factory = FakeClient(name=types.DeviceNameResponse(name="BUSY Bar"))
    status = await NameStep().status(factory)  # type: ignore[arg-type]
    assert status.done is False
    assert "factory default" in status.summary

    renamed = FakeClient(name=types.DeviceNameResponse(name="Front desk"))
    assert (await NameStep().status(renamed)).done is True  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_cloud_step_status() -> None:
    """
    Report the cloud step as done only once the device is linked.
    """
    linked = FakeClient(
        account_info=types.AccountInfo(linked=True, email="a@example.com")
    )
    status = await CloudStep().status(linked)  # type: ignore[arg-type]
    assert status.done is True
    assert status.summary == "a@example.com"

    unlinked = FakeClient(account_info=types.AccountInfo(linked=False))
    assert (await CloudStep().status(unlinked)).done is False  # type: ignore[arg-type]


class _StubStep(SetupStep):
    """
    Step with a fixed status that records whether it was run.
    """

    def __init__(self, key: str, done: bool) -> None:
        self.key = key
        self.title = key.title()
        self._done = done
        self.ran = False

    async def status(self, client) -> StepStatus:
        return StepStatus(done=self._done, summary="stub")

    async def run(self, client, prompt) -> None:
        self.ran = True


@pytest.mark.asyncio
async def test_run_setup_skips_completed_steps() -> None:
    """
    Only pending steps are executed, and completed ones are shown as done.
    """
    done_step = _StubStep("alpha", done=True)
    pending_step = _StubStep("beta", done=False)

    prompt = RecordingPrompt()
    await run_setup(FakeClient(), prompt, steps=[done_step, pending_step])  # type: ignore[arg-type]

    assert done_step.ran is False
    assert pending_step.ran is True
    rendered = "\n".join(prompt.lines)
    assert "[x] Alpha" in rendered
    assert "[ ] Beta" in rendered


@pytest.mark.asyncio
async def test_run_setup_redo_runs_completed_steps() -> None:
    """
    `redo` re-runs steps the device already satisfies.
    """
    done_step = _StubStep("alpha", done=True)
    prompt = RecordingPrompt()
    await run_setup(FakeClient(), prompt, steps=[done_step], redo=True)  # type: ignore[arg-type]
    assert done_step.ran is True


@pytest.mark.asyncio
async def test_run_setup_only_restricts_to_one_step() -> None:
    """
    `only` runs a single step and leaves the others alone.
    """
    first = _StubStep("alpha", done=False)
    second = _StubStep("beta", done=False)
    prompt = RecordingPrompt()
    await run_setup(FakeClient(), prompt, steps=[first, second], only="beta")  # type: ignore[arg-type]
    assert first.ran is False
    assert second.ran is True


@pytest.mark.asyncio
async def test_collect_status_isolates_failures() -> None:
    """
    One unreadable step doesn't hide the state of the others.
    """
    client = FakeClient(
        version=RuntimeError("boom"),
        name=types.DeviceNameResponse(name="Front desk"),
    )
    reports = await collect_status(client, [FirmwareStep(), NameStep()])  # type: ignore[arg-type]

    assert reports[0].error is not None
    assert "could not read" in reports[0].render()
    assert reports[1].done is True


@pytest.mark.asyncio
async def test_run_setup_reports_step_failure_without_aborting() -> None:
    """
    A failing step is reported and the run continues to the next one.
    """

    class _Failing(_StubStep):
        async def run(self, client, prompt) -> None:
            raise RuntimeError("nope")

    failing = _Failing("alpha", done=False)
    following = _StubStep("beta", done=False)

    prompt = RecordingPrompt()
    await run_setup(FakeClient(), prompt, steps=[failing, following])  # type: ignore[arg-type]

    assert following.ran is True
    assert any("failed: nope" in line for line in prompt.lines)


class _UpdateClient:
    """
    Replays a sequence of `/api/update/status` responses.
    """

    def __init__(self, sequence: list[types.UpdateStatus]) -> None:
        self._sequence = list(sequence)
        self.checks = 0

    async def update_check(self):
        self.checks += 1
        return types.SuccessResponse(result="OK")

    async def update_status(self):
        if len(self._sequence) > 1:
            return self._sequence.pop(0)
        return self._sequence[0]

    async def update_install(self, version: str):
        self.installed = version
        return types.SuccessResponse(result="OK")


def _check(status: str, version: str | None = None) -> types.UpdateStatus:
    return types.UpdateStatus(
        check=types.UpdateCheckStatus(status=status, available_version=version)
    )


@pytest.mark.asyncio
async def test_firmware_keeps_polling_while_the_check_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    A check still in progress must not be read as "no update available".

    The device reports status "none" until the check produces a result, so
    treating any non-idle status as terminal skipped the first-run update.
    """
    monkeypatch.setattr(steps, "UPDATE_POLL_INTERVAL_SECONDS", 0)
    client = _UpdateClient(
        [_check("none"), _check("none"), _check("available", "1.1.1")]
    )

    prompt = RecordingPrompt([True])
    await FirmwareStep().run(client, prompt)  # type: ignore[arg-type]

    assert any("1.1.1" in line for line in prompt.lines)


@pytest.mark.asyncio
async def test_firmware_stops_on_a_terminal_no_update_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    `not_available` ends the poll without offering an install.
    """
    monkeypatch.setattr(steps, "UPDATE_POLL_INTERVAL_SECONDS", 0)
    client = _UpdateClient([_check("not_available")])

    prompt = RecordingPrompt()
    await FirmwareStep().run(client, prompt)  # type: ignore[arg-type]

    assert any("No update is offered" in line for line in prompt.lines)


@pytest.mark.parametrize(
    "offset,expected",
    [
        (timedelta(hours=3), "+3"),
        (timedelta(0), "+0"),
        (timedelta(hours=-8), "-8"),
        (timedelta(hours=5, minutes=30), None),
        (timedelta(hours=12, minutes=45), None),
    ],
)
def test_offset_label_skips_offsets_with_minutes(
    offset: timedelta, expected: str | None
) -> None:
    """
    Only whole-hour offsets are offered as a timezone default.

    `resolve_timezone` rejects offsets with minutes, so suggesting "+5" to
    somebody in +05:30 would be actively misleading.
    """
    assert steps._whole_hour_offset_label(offset) == expected
