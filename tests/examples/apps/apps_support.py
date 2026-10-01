"""
Doubles shared by the app manager's tests: a GitHub that answers from a
table, a bar that keeps its apps in a list, and archives built in memory.
"""

from __future__ import annotations

import io
import json
import tarfile
from pathlib import Path

from busylib import types
from examples.apps.bar import Bar
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
        self.done.append("quit")

    async def delete(self, app_id: str) -> None:
        self.done.append(f"delete {app_id}")
        self.apps = [a for a in self.apps if a.id != app_id]


def manager_for(
    tmp_path: Path, bar: Bar | None, routes: dict | None = None, **kwargs
) -> Manager:
    return Manager(
        Store(tmp_path / "apps.json"),
        GitHub(Net(routes or {}), token=""),
        Launcher(tmp_path / "logs"),
        bar,
        **kwargs,
    )
