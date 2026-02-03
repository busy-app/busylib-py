from __future__ import annotations

import pytest

from examples.remote import periodic_tasks as remote_periodic


class DummyClient:
    """
    Minimal client stub for periodic task tests.
    """

    def __init__(self) -> None:
        """
        Initialize with a local connection flag.
        """
        self.is_local = True

    async def is_local_available(self) -> bool:
        """
        Report local API availability.
        """
        return True

    async def get_account_info(self):
        """
        Report unlinked account status.
        """

        class _Info:
            linked = False

        return _Info()

    async def link_account(self):
        """
        Report account link code.
        """

        class _Link:
            code = "WXYZ"

        return _Link()

    async def check_firmware_update(self):
        """
        Track update checks.
        """
        return None

    async def get_update_status(self):
        """
        Report available update status.
        """

        class _Check:
            available_version = "1.2.3"

        class _Status:
            check = _Check()

        return _Status()


class DummyRenderer:
    """
    Minimal renderer stub for periodic task tests.
    """

    def __init__(self) -> None:
        """
        Initialize with empty info tracking.
        """
        self.snapshots: list[object] = []
        self.usb_states: list[bool] = []
        self.link_states: list[bool] = []
        self.link_keys: list[str] = []
        self.update_states: list[bool] = []

    def update_info(
        self,
        snapshot=None,
        usb_connected=None,
        streaming_info=None,
        link_connected=None,
        link_key=None,
        update_available=None,
    ) -> None:
        """
        Record snapshot and USB updates for assertions.
        """
        if snapshot is not None:
            self.snapshots.append(snapshot)
        if usb_connected is not None:
            self.usb_states.append(usb_connected)
        if link_connected is not None:
            self.link_states.append(link_connected)
        if link_key is not None:
            self.link_keys.append(link_key)
        if update_available is not None:
            self.update_states.append(update_available)


@pytest.mark.asyncio
async def test_build_periodic_tasks_runs_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    """
    Ensure periodic task callables execute and update the renderer.
    """

    async def fake_snapshot(_client) -> object:
        return {"ok": True}

    monkeypatch.setattr(remote_periodic, "collect_device_snapshot", fake_snapshot)

    client = DummyClient()
    renderer = DummyRenderer()
    tasks = {
        "info_update": (remote_periodic.dashboard, 1),
        "usb_check": (remote_periodic.usb, 5),
        "link_check": (remote_periodic.cloud_link, 10),
        "update_check": (remote_periodic.update_check, 3600),
    }
    task_map = remote_periodic.build_periodic_tasks(
        client,
        renderer,
        tasks=tasks,
    )

    interval, task = task_map["info_update"]
    assert interval == tasks["info_update"][1]
    await task()
    assert renderer.snapshots == [{"ok": True}]

    interval, task = task_map["usb_check"]
    assert interval == tasks["usb_check"][1]
    await task()
    assert renderer.usb_states == [True]

    interval, task = task_map["link_check"]
    assert interval == tasks["link_check"][1]
    await task()
    assert renderer.link_states == [False]
    assert renderer.link_keys == ["WXYZ"]

    interval, task = task_map["update_check"]
    assert interval == tasks["update_check"][1]
    await task()
    assert renderer.update_states == [True]
