"""
The manager's terminal interface.

A list of everything that can be started - applications on the bar and
programs on this computer - with a card for the one under the cursor, as in
the other terminal tools of ours; and a dashboard of the same things as cards,
for starting rather than managing.
"""

from __future__ import annotations

import webbrowser
from collections.abc import Awaitable, Callable
from pathlib import Path

from textual import events, on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.css.query import NoMatches
from textual.containers import Grid, Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Markdown, Static

from .dialogs import (
    SECRET_NAME,
    Confirm,
    Field,
    FormModal,
    Pick,
    Progress,
    ProgramPick,
    Sources,
    Verdict,
    Versions,
    ask_for_source,
)
from . import link
from .launcher import format_env
from .bar import CannotQuitDirectly
from .manager import Entry, Manager
from .mirror import Mirror
from .model import ManagerError
from .logview import LogScreen
from .mirror import KEYS
from .view import BarScreen, Key, Pad


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

    if entry.kind == "available":
        lines = [f"## {entry.name}", ""]
        meta = " · ".join(part for part in (entry.version, entry.author) if part)
        if meta:
            lines += [f"**{meta}**", ""]
        if entry.description:
            lines += [entry.description, ""]
        lines += [
            f"Not installed · offered by `{entry.origin}` · would go on "
            f"{'the bar' if entry.where == 'bar' else 'this computer'}",
            "",
            "**Enter** or **i** install · **d** forget the source",
        ]
        return "\n".join(lines)

    app = entry.external
    assert app is not None
    lines = [f"## {entry.name}", ""]
    if entry.description:
        lines += [entry.description, ""]
    if entry.origin:
        note = " - **update available**, press `u`" if entry.update else ""
        lines += [f"**From** {entry.origin}{note}", ""]
    lines += [
        f"**Folder** `{app.path}`",
        "",
        "**Runs as**",
        "",
        "```",
        manager.launcher.command_for(app),
        "```",
        "",
    ]
    if app.env:
        # The names, never the values: a key typed into a form is a secret.
        lines += [f"**Environment** {', '.join(sorted(app.env))} (set)", ""]
    lines += [f"On this computer · {entry.status}", ""]
    keys = ["**Enter** run", "**x** stop", "**m** modify"]
    if entry.origin:
        keys += ["**c** settings", "**o** page", "**d** remove"]
    else:
        keys += ["**d** forget"]
    lines += [" · ".join(keys)]
    tail = manager.launcher.tail(app)
    if tail:
        lines += ["", "**Last output**", "", "```", tail, "```"]
    return "\n".join(lines)


class Home(Screen[None]):
    BINDINGS = [
        Binding("i", "install", "Install"),
        Binding("a", "add_source", "Add source"),
        Binding("s", "sources", "Sources", show=False),
        Binding("l", "logs", "Logs"),
        Binding("backspace", "press('back')", "Back", show=False),
        Binding("k", "press('ok')", "OK", show=False),
        Binding("space", "press('start')", "Start", show=False),
        Binding("left_square_bracket", "press('left')", "Scroll ◀", show=False),
        Binding("right_square_bracket", "press('right')", "Scroll ▶", show=False),
        Binding("1", "press('busy')", "Busy", show=False),
        Binding("2", "press('custom')", "Custom", show=False),
        Binding("3", "press('off')", "Off", show=False),
        Binding("4", "press('apps')", "Apps", show=False),
        Binding("5", "press('settings')", "Settings", show=False),
        Binding("x", "stop", "Quit/stop"),
        Binding("d", "remove", "Remove"),
        Binding("e", "add_external", "Add external"),
        Binding("m", "modify", "Modify"),
        Binding("u", "update", "Update"),
        Binding("c", "settings", "Settings"),
        Binding("o", "open_page", "Open page", show=False),
        Binding("b", "dashboard", "Dashboard"),
        Binding("r", "refresh", "Refresh"),
        Binding("q", "app.quit", "Quit"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.entries: dict[str, Entry] = {}
        # What the card was last asked to show. The widget keeps it too, but
        # under a name that has changed between releases of Textual.
        self.card = ""
        # Sentences about things that went wrong in the background, shown in
        # the banner until the next check says otherwise.
        self.notices: list[str] = []
        # What listing the bar last complained about.
        self.problem = ""

    @property
    def manager(self) -> Manager:
        return self.app.manager  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("", id="banner")
        with Horizontal(id="view"):
            yield BarScreen()
            yield Pad(id="pad")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield DataTable(id="apps", cursor_type="row", zebra_stripes=True)
            with VerticalScroll(id="right"):
                yield Markdown("", id="details")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#view").display = self.manager.bar is not None
        table = self.query_one(DataTable)
        table.add_column("Name", key="name")
        table.add_column("Where", key="where")
        table.add_column("Version", key="version")
        table.add_column("Status", key="status")
        self.set_interval(2.0, self.tick)
        self.run_worker(self.reload(), exclusive=True, group="reload")
        self.run_worker(self.check_updates(), exclusive=True, group="updates")

    # Showing -----------------------------------------------------------

    async def reload(self, keep: str | None = None) -> None:
        entries, problem = await self.manager.entries()
        self.problem = problem
        self.show_banner()

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

    def show_banner(self) -> None:
        """
        The one line above the list that says what is wrong right now.
        """
        sentences = [
            item
            for item in (
                self.app.link_problem,  # type: ignore[attr-defined]
                self.problem,
                self.manager.store.warning,
                *self.notices,
            )
            if item
        ]
        try:
            banner = self.query_one("#banner", Static)
        except NoMatches:
            return  # not drawn yet; the next reload draws it from the same state
        banner.update(" · ".join(dict.fromkeys(sentences)))
        banner.display = bool(sentences)

    async def check_updates(self) -> None:
        """
        Ask the sources what they have now, so that what is available is true
        and installed programs can say they are out of date. Quiet when there
        is nothing to ask.
        """
        if not self.manager.store.config.sources:
            return
        self.notices = await self.manager.refresh_sources()
        await self.reload()

    def tick(self) -> None:
        """
        Keep the status of external apps true while they start and stop on
        their own - which they do, without anyone pressing anything.
        """
        table = self.query_one(DataTable)
        for key, entry in self.entries.items():
            if entry.external is None:
                continue
            now = entry.with_running(self.manager.launcher.is_running(entry.external))
            if now.status != entry.status:
                self.entries[key] = now
                table.update_cell(key, "status", now.status)
                if key == self.current_key():
                    self.show(now)

    def current_key(self) -> str | None:
        table = self.query_one(DataTable)
        if not table.row_count:
            return None
        return table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value

    def current(self) -> Entry | None:
        key = self.current_key()
        return self.entries.get(key) if key else None

    def show(self, entry: Entry | None) -> None:
        if entry is None:
            self.card = (
                "## Nothing here yet\n\n"
                "**i** installs an app on the bar from a source.\n\n"
                "**e** adds a program on this computer."
            )
        else:
            self.card = describe(entry, self.manager)
        self.query_one("#details", Markdown).update(self.card)

    @on(DataTable.RowHighlighted)
    def highlighted(self) -> None:
        self.show(self.current())

    @on(DataTable.RowSelected)
    async def selected(self) -> None:
        entry = self.current()
        if entry is not None:
            if entry.kind == "available":
                self.install_offer(entry)
                return
            await self.app.attempt(self.manager.activate(entry))  # type: ignore[attr-defined]
            self.tick()

    # Actions -----------------------------------------------------------

    def action_refresh(self) -> None:
        self.run_worker(self.reload(), exclusive=True, group="reload")
        self.app.notify("Refreshing")

    @work
    async def action_stop(self) -> None:
        await self.app.stop(self.current())  # type: ignore[attr-defined]
        self.tick()

    @work
    async def action_remove(self) -> None:
        entry = self.current()
        if entry is None:
            return
        if entry.kind == "available":
            source = self.manager.source_of(entry)
            if source is not None and await self.app.push_screen_wait(
                Confirm(
                    f"Forget the source {source.repo}?",
                    "Everything it offers leaves the list. Nothing installed is "
                    "touched.",
                    ok="Forget",
                    variant="error",
                )
            ):
                self.manager.forget_source(source)
                await self.reload()
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
                values["name"],
                values["path"],
                values["command"],
                values["description"],
                values["env"],
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
                        placeholder="python main.py --host {host}",
                        hint="{host} is the bar this manager is connected to; "
                        "{python} is the Python running it.",
                    ),
                    Field("description", "About it", placeholder="One line"),
                    Field(
                        "env",
                        "Environment",
                        placeholder="CITY=Utrecht",
                        hint="Optional KEY=value pairs, set when it runs.",
                    ),
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
                values["env"],
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
                    Field("env", "Environment", value=format_env(app.env)),
                ],
                check=check,
            )
        )
        if changed is not None:
            await self.reload(keep=entry.key)

    @work
    async def action_add_source(self) -> None:
        if await ask_for_source(self.app):
            await self.reload()

    @work
    async def action_install(self) -> None:
        """
        Install the one under the cursor if it is on offer; otherwise choose
        from the sources.
        """
        entry = self.current()
        if entry is not None and entry.kind == "available":
            await self.install_offer_now(entry)
        else:
            await self.choose_from_sources()

    def action_logs(self) -> None:
        if self.manager.bar is None:
            self.app.notify("There is no bar to read logs from", severity="warning")
            return
        self.app.push_screen(LogScreen())

    @on(Button.Pressed)
    def pad_pressed(self, event: Button.Pressed) -> None:
        if isinstance(event.button, Key):
            self.action_press((event.button.id or "").removeprefix("press-"))

    def action_press(self, name: str) -> None:
        """
        Press one of the bar's keys, or move its switch, as a hand would.
        """
        self.run_worker(self._press(name), group="press")

    async def _press(self, name: str) -> None:
        bar = self.manager.bar
        if bar is None:
            self.app.notify("There is no bar to press keys on", severity="warning")
            return
        try:
            await bar.press(KEYS[name])
        except ManagerError as err:
            self.app.notify(str(err), title="Could not press it", severity="error")

    @work
    async def install_offer(self, entry: Entry) -> None:
        await self.install_offer_now(entry)

    async def install_offer_now(self, entry: Entry) -> None:
        """
        Install what a source offers: pick a version of an app, or fetch the
        program from its catalog.
        """
        source = self.manager.source_of(entry)
        if source is None:
            return
        if source.kind == "catalog":
            try:
                catalog = self.manager.catalogs.get(source.repo) or (
                    await self.manager.catalog(source)
                )
            except ManagerError as err:
                self.app.notify(str(err), severity="error")
                return
            program = catalog.find(entry.ident)
            if program is None:
                self.app.notify(
                    f"{source.repo} no longer has {entry.name}", severity="warning"
                )
                return
            await self.install_program(ProgramPick(source, catalog, program))
            return
        version = await self.app.push_screen_wait(
            Versions(source, lambda: self.manager.versions(source))
        )
        if version is not None:
            await self.install(Pick(source, version))

    @work
    async def action_sources(self) -> None:
        await self.choose_from_sources()

    async def choose_from_sources(self) -> None:
        pick = await self.app.push_screen_wait(Sources())
        await self.reload()
        if isinstance(pick, ProgramPick):
            await self.install_program(pick)
        elif pick is not None:
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

    async def install_program(self, pick: ProgramPick, go: str = "Install") -> None:
        """
        Put a program from a catalog on this computer: say what that will do,
        and on a yes, do it. It is code that will run here, so the question is
        not skipped.
        """
        progress = Progress(f"{pick.app.name} - {pick.source.label}", go=go)
        await self.app.push_screen(progress)
        try:
            prepared = await self.manager.prepare_program(
                pick.source, pick.catalog, pick.app
            )
        except ManagerError as err:
            progress.done(str(err), ok=False)
            return
        if not await progress.ask(f"{prepared.summary} Go ahead?"):
            progress.done("Cancelled. Nothing was installed.")
            return
        try:
            program = await self.manager.install_program(prepared, progress.say)
        except ManagerError as err:
            progress.done(str(err), ok=False)
            return
        progress.done(f"{pick.app.name} is on the list. Press Enter on it to run.")
        await self.reload(keep=f"external:{program.slug}")

    @work
    async def action_update(self) -> None:
        entry = self.current()
        if entry is None or entry.external is None or not entry.update:
            self.app.notify("Nothing to update here", severity="warning")
            return
        stamp = self.manager.stamp_of(entry.external)
        catalog = self.manager.catalogs.get(stamp.repo) if stamp else None
        slug = Path(entry.external.path).name
        app = catalog.find(slug) if catalog else None
        source = next(
            (
                s
                for s in self.manager.store.config.sources
                if stamp and s.kind == "catalog" and s.repo == stamp.repo
            ),
            None,
        )
        if catalog is None or app is None or source is None:
            self.app.notify(
                "The catalog is not available; add it again under Sources",
                severity="warning",
            )
            return
        await self.install_program(ProgramPick(source, catalog, app), go="Update")

    @work
    async def action_settings(self) -> None:
        """
        Fill in the variables a program says it reads.
        """
        entry = self.current()
        if entry is None or entry.external is None:
            return
        app = entry.external
        spec = self.manager.env_spec(app)
        if not spec:
            self.app.notify(
                "This program does not declare settings. Use m to set environment by hand.",
                severity="warning",
            )
            return

        async def check(values: dict[str, str]) -> Verdict:
            self.manager.set_env(app, values)
            return None

        saved = await self.app.push_screen_wait(
            FormModal(
                f"Settings for {app.name}",
                [
                    Field(
                        var.key,
                        var.key,
                        value=app.env.get(var.key, ""),
                        placeholder=var.example,
                        hint=var.help,
                        secret=bool(SECRET_NAME.search(var.key)),
                    )
                    for var in spec
                ],
                check=check,
            )
        )
        if saved is not None:
            self.app.notify("Saved. It takes effect the next time it runs.")
            await self.reload(keep=entry.key)

    def action_open_page(self) -> None:
        entry = self.current()
        url = self.manager.page_url(entry) if entry else None
        if url is None:
            self.app.notify("No page for this one", severity="warning")
            return
        webbrowser.open(url)
        self.app.notify(url)

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
        entries = [entry for entry in entries if entry.kind != "available"]
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
            now = card.entry.with_running(self.manager.launcher.is_running(app))
            if now.status != card.entry.status:
                card.entry = now
                card.set_classes(f"card {now.kind} {now.status}")
                card.refresh()

    def action_refresh(self) -> None:
        self.run_worker(self.load(), exclusive=True)

    @work
    async def action_stop(self) -> None:
        focused = self.focused
        entry = focused.entry if isinstance(focused, AppCard) else None
        await self.app.stop(entry)  # type: ignore[attr-defined]
        self.tick()

    async def on_key(self, event: events.Key) -> None:
        if event.key == "enter" and isinstance(self.focused, AppCard):
            event.stop()
            await self.app.attempt(self.manager.activate(self.focused.entry))  # type: ignore[attr-defined]
            self.tick()


class AppsManager(App[None]):
    TITLE = "BUSY Bar Manager"
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
        self.home = Home()
        self.mirror = Mirror()
        # Said in the banner while the bar is away; empty when it is there.
        self.link_problem = ""

    @property
    def screen_note(self) -> str:
        """
        What the display area says when there is no picture to show.
        """
        if self.manager.bar is None:
            return "no bar"
        return "not connected" if self.link_problem else "waiting for the display..."

    async def load_picture(self) -> None:
        """
        The display as it is now, for the moment before the stream has sent a
        frame of its own - which it does only when something changes.
        """
        bar = self.manager.bar
        data = await bar.front_screen() if bar is not None else None
        if data and self.mirror.frame is None:
            self.mirror.show_screen(data)

    async def on_mount(self) -> None:
        if self.manager.bar is not None:
            self.manager.bar.listen(self.mirror.feed)
        self.set_link("no bar" if self.manager.bar is None else "connecting...")
        # Waited for, because the watch reports into the list's own window: a
        # report that arrives before it exists would fail inside the watch and
        # end it, and the connection would go unwatched with nothing to say so.
        await self.push_screen(self.home)
        if self.manager.bar is not None:
            self.run_worker(self.keep_link(), exclusive=True, group="link")

    def set_link(self, state: str) -> None:
        """
        Put the state of the connection in the title bar, where it is always
        in sight whichever window is open.
        """
        self.sub_title = f"{self.address} - {state}" if self.address else state

    async def keep_link(self) -> None:
        bar = self.manager.bar
        assert bar is not None
        await link.watch(bar, self.on_link)

    def on_link(self, event: link.Event) -> None:
        """
        The bar went, or came back. Say so in the title bar and in a toast,
        and when it is back, look again: a bar that has been restarted may
        have different apps, or a different firmware.
        """
        if isinstance(event, link.Down):
            self.link_problem = "the bar is not answering - trying again"
            self.mirror.clear()
            if event.first:
                self.set_link("not reachable - retrying")
                self.notify(
                    f"Cannot reach the bar: {event.reason}. Trying again.",
                    title="Not connected",
                    severity="error",
                    timeout=10,
                )
            else:
                self.set_link("connection lost - retrying")
                self.notify(
                    f"Lost the connection to the bar ({event.reason}). Trying again.",
                    title="Disconnected",
                    severity="warning",
                    timeout=10,
                )
        else:
            self.link_problem = ""
            self.run_worker(self.load_picture(), group="picture")
            self.set_link(f"connected, API {event.api}" if event.api else "connected")
            if event.after is not None:
                gone = f"{event.after:.0f} s"
                self.notify(
                    f"Connected again after {gone}."
                    if event.previous
                    else f"Connected to the bar after {gone}.",
                    title="Connected",
                )
            if event.previous and event.api and event.previous != event.api:
                self.notify(
                    f"The bar's API went from {event.previous} to {event.api}: "
                    "its firmware changed.",
                    title="Firmware changed",
                )
            self.home.run_worker(self.home.reload(), exclusive=True, group="reload")
        self.home.show_banner()

    async def on_unmount(self) -> None:
        if self._close is not None:
            await self._close()

    async def stop(self, entry: Entry | None) -> bool:
        """
        Stop what the entry stands for. If the bar cannot be asked to quit its
        app, say what the other way does and ask before taking it.

        Must run in a worker, since it waits on a window.
        """
        try:
            message = await self.manager.stop(entry)
        except CannotQuitDirectly as err:
            agreed = await self.push_screen_wait(
                Confirm(
                    "Stop the app by moving the switch?",
                    f"{err}. The other way is to press Back and then move the "
                    "bar's switch to Off and back to Apps, which ends the app "
                    "and leaves the bar on the Apps menu. The displays go "
                    "dark for a moment, and whatever was showing is replaced.",
                    ok="Stop the app",
                    variant="warning",
                )
            )
            if not agreed:
                return False
            return await self.attempt(self.manager.stop(entry, by_switch=True))
        except ManagerError as err:
            self.notify(
                str(err), title="Could not do that", severity="error", timeout=10
            )
            return False
        self.notify(message)
        return True

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
