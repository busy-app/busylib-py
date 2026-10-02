"""
Doubles shared by the app manager's tests: a GitHub that answers from a
table, a bar that keeps its apps in a list, and archives built in memory.
"""

from __future__ import annotations

import asyncio
import io
import json
import tarfile
from pathlib import Path

from busylib import types
from examples.apps import catalog as catalog_module
from examples.apps.bar import Bar, CannotQuitDirectly
from examples.apps.github import GitHub, Reply
from examples.apps.launcher import Launcher
from examples.apps.manager import Manager
from examples.apps.model import ManagerError
from examples.apps.store import Store

MANIFEST = json.dumps(
    {"id": "demo.app", "name": "Demo", "version": "1.2.0", "description": "A demo"}
).encode()

RELEASES = "https://api.github.com/repos/busy-app/demo/releases?per_page=30"
RELEASE = {
    "tag_name": "v1.2.0",
    "published_at": "2026-09-30T00:00:00Z",
    "assets": [
        {"name": "demo.tgz", "browser_download_url": "https://dl/demo.tgz", "size": 1}
    ],
}


def tgz(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


class Net:
    def __init__(self, routes: dict[str, Reply | object]) -> None:
        self.routes = routes

    def __call__(self, url: str, headers: dict[str, str], limit: int) -> Reply:
        answer = self.routes.get(url, Reply(404))
        return (
            answer
            if isinstance(answer, Reply)
            else Reply(200, json.dumps(answer).encode())
        )


class FakeBar(Bar):
    """
    A bar that keeps its apps in a list and records what was done to it.
    """

    def __init__(self, apps: list[types.AppInfo] | None = None) -> None:
        super().__init__(client=None)  # type: ignore[arg-type]
        self.apps = apps or []
        self.done: list[str] = []
        self.staged_package: bytes = b""
        self.broken: str = ""
        # What asking the bar to quit its app comes to: "works" (the
        # default), "unavailable" (old firmware), or "none running".
        self.quit_answer = "works"
        # What the display shows when asked for outright, before the stream
        # has said anything.
        self.picture: bytes | None = None
        # What the bar's log dump holds, or why it cannot be had.
        self.log: bytes = b""
        self.log_problem = ""
        # The connection: the API it reports, whether it answers, and the
        # socket the manager holds open to it.
        self.api = "27.9.0"
        self.online = True
        self._socket: asyncio.Event | None = None

    def _event(self) -> asyncio.Event:
        # Made on first use, inside the loop that will wait on it.
        if self._socket is None:
            self._socket = asyncio.Event()
        return self._socket

    async def version(self, timeout: float = 4.0) -> str:
        if not self.online:
            raise ManagerError("the bar did not answer (connection refused)")
        return self.api

    async def hold(self) -> None:
        """
        An open socket: returns only when the bar is told to go away.
        """
        if not self.online:
            raise ManagerError("the bar did not answer (connection refused)")
        event = self._event()
        await event.wait()
        event.clear()
        raise ManagerError("the connection closed")

    def go_away(self) -> None:
        self.online = False
        self._event().set()

    def come_back(self, api: str | None = None) -> None:
        self.online = True
        if api is not None:
            self.api = api

    async def installed(self) -> list[types.AppInfo]:
        if self.broken:
            raise ManagerError(self.broken)
        return list(self.apps)

    async def stage(self, package: bytes) -> types.AppStageResult:
        self.staged_package = package
        with tarfile.open(fileobj=io.BytesIO(package)) as tar:
            member = next(m for m in tar if m.name.endswith("manifest.json"))
            raw = json.loads(tar.extractfile(member).read())  # type: ignore[union-attr]
        old = next((a for a in self.apps if a.id == raw["id"]), None)
        return types.AppStageResult(
            result="OK",
            install_key=5,
            staged=types.AppInfo(
                id=raw["id"], name=raw["name"], version=raw["version"]
            ),
            installed=old,
        )

    async def install(self, staged: types.AppStageResult) -> None:
        self.done.append(f"install {staged.install_key}")
        self.apps = [a for a in self.apps if a.id != staged.staged.id] + [staged.staged]

    async def launch(self, app_id: str) -> None:
        self.done.append(f"launch {app_id}")

    async def quit(self) -> None:
        if self.quit_answer == "unavailable":
            raise CannotQuitDirectly("this bar's firmware has no way to quit an app")
        if self.quit_answer == "none running":
            raise ManagerError("no app is running on the bar")
        self.done.append("quit")

    async def leave_by_switch(self, pause: float = 1.5, sleep=None) -> None:
        self.done.append("switch")

    async def fetch_log(self) -> bytes:
        if self.log_problem:
            raise ManagerError(self.log_problem)
        return self.log

    async def front_screen(self) -> bytes | None:
        return self.picture

    async def press(self, key: types.InputKey) -> None:
        self.done.append(f"press {key.name}")

    def emit(self, message: dict) -> None:
        """
        Say something on the socket the manager holds, as the bar would.
        """
        for callback in list(self._listeners):
            callback(message)

    async def delete(self, app_id: str) -> None:
        self.done.append(f"delete {app_id}")
        self.apps = [a for a in self.apps if a.id != app_id]


def manager_for(
    tmp_path: Path, bar: Bar | None, routes: dict | None = None, **kwargs
) -> Manager:
    return Manager(
        Store(tmp_path / "apps.db"),
        GitHub(Net(routes or {}), token=""),
        Launcher(tmp_path / "logs"),
        bar,
        **kwargs,
    )


# A repository of programs, as GitHub would serve it -------------------------------

BRANCH = "https://api.github.com/repos/busy-app/programs/branches/main"
TREE = "https://api.github.com/repos/busy-app/programs/git/trees/c0ffee?recursive=1"
RAW = "https://raw.githubusercontent.com/busy-app/programs/c0ffee"


def manifest_bytes(name: str) -> bytes:
    return (
        f"name: {name}\nauthor: me\ndescription: About {name}\ntags:\n  - x\n".encode()
    )


class CatalogNet:
    """
    A repository of programs, with the counts of what was asked of it.
    """

    def __init__(self, programs: dict[str, dict[str, bytes]]) -> None:
        self.programs = programs
        self.asked: list[tuple[str, bool]] = []

    def tree(self) -> dict:
        return {
            "truncated": False,
            "tree": [
                {
                    "type": "blob",
                    "path": f"apps/{slug}/{name}",
                    "sha": catalog_module.git_blob_sha(data),
                    "size": len(data),
                }
                for slug, files in self.programs.items()
                for name, data in files.items()
            ],
        }

    def __call__(self, url: str, headers: dict[str, str], limit: int) -> Reply:
        self.asked.append((url, "If-None-Match" in headers))
        if url == BRANCH:
            return self._json({"commit": {"sha": "c0ffee"}}, "b1")
        if url == TREE:
            return self._json(self.tree(), "t1")
        if url.startswith(RAW + "/apps/"):
            _, _, slug, name = url.removeprefix(RAW).split("/", 3)
            data = self.programs.get(slug, {}).get(name)
            return Reply(200, data) if data is not None else Reply(404)
        return Reply(404)

    def _json(self, body: object, etag: str) -> Reply:
        return Reply(200, json.dumps(body).encode(), {"etag": etag})


def program(name: str) -> dict[str, bytes]:
    return {"app.py": b"print('hi')\n", "manifest.yaml": manifest_bytes(name)}


def manager_with_catalog(tmp_path: Path, programs: dict, bar=None, **kwargs):
    """
    A manager whose GitHub is a catalog of `programs`, and that net.
    """
    net = CatalogNet(programs)
    manager = manager_for(tmp_path, bar, **kwargs)
    manager.github.fetch = net
    return net, manager
