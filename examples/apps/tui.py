"""
The manager's terminal interface.

A list of everything that can be started - applications on the bar and
programs on this computer - with a card for the one under the cursor, as in
the other terminal tools of ours; and a dashboard of the same things as cards,
for starting rather than managing.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path

from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Markdown, Static

from .dialogs import Confirm, Field, FormModal, Pick, Progress, Sources, Verdict
from .manager import Entry, Manager
from .model import ManagerError


def describe(entry: Entry, manager: Manager) -> str:
    """
    The card for an entry, as Markdown.
    """
    if entry.kind == "bar":
        lines = [f"## {entry.name}", ""]
        meta = " · ".join(part for part in (entry.version, entry.author) if part)
        if meta:
            lines += [f"**{meta}**", ""]
        if entry.description:
            lines += [entry.description, ""]
        lines += [f"`{entry.ident}` · on the bar", ""]
        if entry.info is not None and entry.info.is_debug:
            lines += ["_A debug app: the bar shows it only in debug mode._", ""]
        lines += ["**Enter** launch · **x** quit the running app · **d** remove"]
        return "\n".join(lines)

    app = entry.external
    assert app is not None
    lines = [f"## {entry.name}", ""]
    if entry.description:
        lines += [entry.description, ""]
    lines += [
        f"**Folder** `{app.path}`",
        "",
        "**Command**",
        "",
        "```",
        app.command,
        "```",
        "",
        f"On this computer · {entry.status}",
        "",
        "**Enter** run · **x** stop · **m** modify · **d** forget",
    ]
    tail = manager.launcher.tail(app)
    if tail:
        lines += ["", "**Last output**", "", "```", tail, "```"]
    return "\n".join(lines)


class Home(Screen[None]):
    BINDINGS = [
        Binding("i", "sources", "Install"),
        Binding("s", "sources", "Sources", show=False),
        Binding("x", "stop", "Quit/stop"),
        Binding("d", "remove", "Remove"),
        Binding("e", "add_external", "Add external"),
        Binding("m", "modify", "Modify"),
        Binding("b", "dashboard", "Dashboard"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.entries: dict[str, Entry] = {}

    @property
    def manager(self) -> Manager:
        return self.app.manager  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="banner")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield DataTable(id="apps", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="right"):
                yield Markdown("", id="details")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column("Name", key="name")
        table.add_column("Where", key="where")
        table.add_column("Version", key="version")
        table.add_column("Status", key="status")
        self.set_interval(2.0, self.tick)
        self.run_worker(self.reload(), exclusive=True, group="reload")

    # Showing -----------------------------------------------------------

    async def reload(self, keep: str | None = None) -> None:
        entries, problem = await self.manager.entries()
        warning = self.manager.store.warning
        banner = self.query_one("#banner", Static)
        banner.update(" · ".join(item for item in (problem, warning) if item))
        banner.display = bool(problem or warning)

        table = self.query_one(DataTable)
        remembered = keep or self.current_key()
        table.clear()
        self.entries = {entry.key: entry for entry in entries}
        for entry in entries:
            table.add_row(
                entry.name,
                entry.where,
                entry.version or "-",
                entry.status,
                key=entry.key,
            )
        if remembered in self.entries:
            table.move_cursor(row=table.get_row_index(remembered))
        self.show(self.current())

    def tick(self) -> None:
        """
        Keep the status of external apps true while they start and stop on
        their own - which they do, without anyone pressing anything.
        """
        table = self.query_one(DataTable)
        for key, entry in self.entries.items():
            if entry.external is None:
                continue
            status = (
                "running"
                if self.manager.launcher.is_running(entry.external)
                else "ready"
            )
            if status != entry.status:
                self.entries[key] = replace(entry, status=status)
                table.update_cell(key, "status", status)
                if key == self.current_key():
                    self.show(self.entries[key])

    def current_key(self) -> str | None:
        table = self.query_one(DataTable)
        if not table.row_count:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    def current(self) -> Entry | None:
        key = self.current_key()
        return self.entries.get(key) if key else None

    def show(self, entry: Entry | None) -> None:
        details = self.query_one("#details", Markdown)
        if entry is None:
            details.update(
                "## Nothing here yet\n\n"
                "**i** installs an app on the bar from a source.\n\n"
                "**e** adds a program on this computer."
            )
            return
        details.update(describe(entry, self.manager))

    @on(DataTable.RowHighlighted)
    def highlighted(self) -> None:
        self.show(self.current())

    @on(DataTable.RowSelected)
    async def selected(self) -> None:
        entry = self.current()
        if entry is not None:
            await self.app.attempt(self.manager.activate(entry))  # type: ignore[attr-defined]
            self.tick()

    # Actions -----------------------------------------------------------

    def action_refresh(self) -> None:
        self.run_worker(self.reload(), exclusive=True, group="reload")
        self.app.notify("Refreshing")

    async def action_stop(self) -> None:
        await self.app.attempt(self.manager.stop(self.current()))  # type: ignore[attr-defined]
        self.tick()

    @work
    async def action_remove(self) -> None:
        entry = self.current()
        if entry is None:
            return
        if entry.kind == "bar":
            heading, body, ok = (
                f"Remove {entry.name} from the bar?",
                "Its settings stay on the bar, so installing it again brings them back.",
                "Remove",
            )
        else:
            heading, body, ok = (
                f"Forget {entry.name}?",
                "The folder and its files are not touched.",
                "Forget",
            )
        if await self.app.push_screen_wait(
            Confirm(heading, body, ok=ok, variant="error")
        ):
            await self.app.attempt(self.manager.remove(entry))  # type: ignore[attr-defined]
            await self.reload()

    @work
    async def action_add_external(self) -> None:
        async def check(values: dict[str, str]) -> Verdict:
            self.manager.add_external(
                values["name"], values["path"], values["command"], values["description"]
            )
            return None

        added = await self.app.push_screen_wait(
            FormModal(
                "Add a program from this computer",
                [
                    Field("name", "Name", placeholder="Meeting light"),
                    Field(
                        "path",
                        "Folder",
                        value=str(Path.cwd()),
                        hint="The command runs here.",
                    ),
                    Field(
                        "command",
                        "Command",
                        placeholder="python main.py --addr 192.168.1.20",
                    ),
                    Field("description", "About it", placeholder="One line"),
                ],
                ok="Add",
                check=check,
            )
        )
        if added is not None:
            await self.reload(
                keep=f"external:{self.manager.store.config.externals[-1].slug}"
            )

    @work
    async def action_modify(self) -> None:
        entry = self.current()
        if entry is None or entry.external is None:
            self.app.notify(
                "Only programs from this computer can be modified", severity="warning"
            )
            return
        app = entry.external

        async def check(values: dict[str, str]) -> Verdict:
            self.manager.edit_external(
                app,
                values["name"],
                values["path"],
                values["command"],
                values["description"],
            )
            return None

        changed = await self.app.push_screen_wait(
            FormModal(
                f"Modify {app.name}",
                [
                    Field("name", "Name", value=app.name),
                    Field("path", "Folder", value=app.path),
                    Field("command", "Command", value=app.command),
                    Field("description", "About it", value=app.description),
                ],
                check=check,
            )
        )
        if changed is not None:
            await self.reload(keep=entry.key)

    @work
    async def action_sources(self) -> None:
        pick = await self.app.push_screen_wait(Sources())
        if pick is not None:
            await self.install(pick)

    async def install(self, pick: Pick) -> None:
        """
        Get a package for the chosen version, show what it will do, and on a
        yes, install it. All in one window that keeps its log.
        """
        progress = Progress(f"{pick.source.label} · {pick.version.label}")
        await self.app.push_screen(progress)
        # The build runs in a thread; the window's `say` is safe from any.
        say = progress.say

        try:
            prepared = await self.manager.prepare(pick.source, pick.version, say)
        except ManagerError as err:
            progress.done(str(err), ok=False)
            return

        if not await progress.ask(f"{prepared.summary} Go ahead?"):
            progress.done(
                "Cancelled. Nothing was installed. The bar keeps the package "
                "until another one is uploaded."
            )
            return

        say("installing")
        try:
            await self.manager.commit(prepared)
        except ManagerError as err:
            progress.done(str(err), ok=False)
            return
        manifest = prepared.package.manifest
        progress.done(f"Installed {manifest.name} {manifest.version}.")
        await self.reload(keep=f"bar:{manifest.id}")

    def action_dashboard(self) -> None:
        self.app.push_screen(Dashboard())


class AppCard(Static, can_focus=True):
    """
    One thing that can be started, as a card.
    """

    def __init__(self, entry: Entry) -> None:
        super().__init__(classes=f"card {entry.kind} {entry.status}")
        self.entry = entry

    def render(self) -> str:
        entry = self.entry
        where = "on the bar" if entry.kind == "bar" else "on this computer"
        detail = entry.description.splitlines()[0] if entry.description else ""
        if len(detail) > 52:
            detail = detail[:51] + "…"
        meta = " · ".join(part for part in (where, entry.version, entry.status) if part)
        return f"[b]{entry.name}[/b]\n[dim]{meta}[/dim]\n{detail}"


class Dashboard(Screen[None]):
    """
    Everything that can be started, as cards: for using, not managing.
    """

    BINDINGS = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("r", "refresh", "Refresh"),
        Binding("left,up", "app.focus_previous", "Previous", show=False),
        Binding("right,down", "app.focus_next", "Next", show=False),
        Binding("x", "stop", "Quit/stop"),
    ]

    @property
    def manager(self) -> Manager:
        return self.app.manager  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="banner")
        yield Grid(id="cards")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = "Dashboard"
        self.run_worker(self.load(), exclusive=True)
        self.set_interval(2.0, self.tick)

    async def load(self) -> None:
        entries, problem = await self.manager.entries()
        banner = self.query_one("#banner", Static)
        banner.update(problem)
        banner.display = bool(problem)
        grid = self.query_one("#cards", Grid)
        await grid.remove_children()
        if not entries:
            await grid.mount(Static("Nothing to start yet. Go back and press i or e."))
            return
        await grid.mount(*[AppCard(entry) for entry in entries])
        grid.query(AppCard).first().focus()

    def tick(self) -> None:
        for card in self.query(AppCard):
            app = card.entry.external
            if app is None:
                continue
            status = "running" if self.manager.launcher.is_running(app) else "ready"
            if status != card.entry.status:
                card.entry = replace(card.entry, status=status)
                card.set_classes(f"card {card.entry.kind} {status}")
                card.refresh()

    def action_refresh(self) -> None:
        self.run_worker(self.load(), exclusive=True)

    async def action_stop(self) -> None:
        focused = self.focused
        entry = focused.entry if isinstance(focused, AppCard) else None
        await self.app.attempt(self.manager.stop(entry))  # type: ignore[attr-defined]
        self.tick()

    async def on_key(self, event: events.Key) -> None:
        if event.key == "enter" and isinstance(self.focused, AppCard):
            event.stop()
            await self.app.attempt(self.manager.activate(self.focused.entry))  # type: ignore[attr-defined]
            self.tick()


class AppsManager(App[None]):
    TITLE = "BUSY Bar apps"
    CSS_PATH = "tui.tcss"
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", show=False)]

    def __init__(
        self,
        manager: Manager,
        address: str = "",
        close: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__()
        self.manager = manager
        self.address = address
        self._close = close

    def on_mount(self) -> None:
        self.sub_title = self.address or "no bar"
        self.push_screen(Home())

    async def on_unmount(self) -> None:
        if self._close is not None:
            await self._close()

    async def attempt(self, work: Awaitable[str]) -> bool:
        """
        Do something that may fail in a way worth explaining, and say how
        it went. A refusal is shown and the interface carries on.
        """
        try:
            message = await work
        except ManagerError as err:
            self.notify(
                str(err), title="Could not do that", severity="error", timeout=10
            )
            return False
        self.notify(message)
        return True
