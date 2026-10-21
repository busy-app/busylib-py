"""
The windows that open over the main list: asking, showing progress, filling
in a form, and choosing a source and a version.

None of them knows how a package is made. They show what the manager tells
them and hand back what the person chose.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Input,
    Label,
    RichLog,
    Select,
    Static,
)

from . import catalog as catalogs
from .manager import Manager
from .model import REPO, ManagerError, Source, Version
from .programs import needs_update


class Confirm(ModalScreen[bool]):
    """
    A question with a yes and a no.
    """

    BINDINGS = [
        Binding("escape", "answer(False)", "Cancel"),
        Binding("y", "answer(True)", "Yes", show=False),
        Binding("n", "answer(False)", "No", show=False),
    ]

    def __init__(
        self,
        heading: str,
        body: str = "",
        *,
        ok: str = "Yes",
        variant: str = "primary",
    ) -> None:
        super().__init__(classes="dialog")
        self.heading = heading
        self.body = body
        self.ok = ok
        self.variant = variant

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.heading, classes="title")
            if self.body:
                yield Static(self.body, classes="body")
            with Horizontal(classes="buttons"):
                yield Button(self.ok, id="yes", variant=self.variant)  # type: ignore[arg-type]
                yield Button("Cancel", id="no")

    def on_mount(self) -> None:
        self.query_one("#no", Button).focus()

    @on(Button.Pressed)
    def pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_answer(self, answer: bool) -> None:
        self.dismiss(answer)


class Progress(ModalScreen[None]):
    """
    A log of what is being done, which can stop and ask before going on.

    One window for the whole of an install, rather than a window for the
    work and another for the question: the question is about what the log
    just said, and the answer continues the log.

    Everything that reaches the screen goes through one queue. Lines come
    from a build running in a thread and from the interface's own task, and
    written directly the two interleave by accident of timing: the question
    would sometimes appear above the lines it is about.
    """

    BINDINGS = [Binding("escape", "leave", "Close")]

    def __init__(self, heading: str, go: str = "Install") -> None:
        super().__init__(classes="dialog wide")
        self.heading = heading
        self.go = go
        self._answer: asyncio.Future[bool] | None = None
        self._finished = False
        self._loop: asyncio.AbstractEventLoop | None = None

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.heading, classes="title")
            yield RichLog(id="log", wrap=True, markup=False, highlight=False)
            with Horizontal(classes="buttons", id="ask"):
                yield Button(self.go, id="go", variant="primary")
                yield Button("Cancel", id="stop")
            with Horizontal(classes="buttons", id="end"):
                yield Button("Close", id="close", variant="primary")

    def on_mount(self) -> None:
        self._loop = asyncio.get_running_loop()
        self.query_one("#ask").display = False
        self.query_one("#end").display = False

    def _later(self, action: Callable[..., object], *args: object) -> None:
        """
        Run `action` on the interface's loop, after everything queued
        before it. Safe from any thread, including that loop's own.
        """
        assert self._loop is not None, "the window has not been shown yet"
        self._loop.call_soon_threadsafe(action, *args)

    def say(self, line: str) -> None:
        self._later(self._write, line)

    def _write(self, line: str) -> None:
        self.query_one("#log", RichLog).write(line)

    async def ask(self, question: str) -> bool:
        """
        Put a question under the log and wait for the answer.
        """
        self._answer = asyncio.get_running_loop().create_future()
        self.say(question)
        self._later(self._show_ask)
        answer = await self._answer
        self.query_one("#ask").display = False
        return answer

    def _show_ask(self) -> None:
        self.query_one("#ask").display = True
        self.query_one("#go", Button).focus()

    def done(self, line: str, *, ok: bool = True) -> None:
        self.say(line)
        self._later(self._show_end, ok)

    def _show_end(self, ok: bool) -> None:
        self._finished = True
        self.query_one("#end").display = True
        self.query_one("#close", Button).focus()
        self.set_class(not ok, "failed")

    @on(Button.Pressed, "#go")
    def go(self) -> None:
        if self._answer and not self._answer.done():
            self._answer.set_result(True)

    @on(Button.Pressed, "#stop")
    def stop(self) -> None:
        if self._answer and not self._answer.done():
            self._answer.set_result(False)

    @on(Button.Pressed, "#close")
    def close(self) -> None:
        self.dismiss(None)

    def action_leave(self) -> None:
        if self._answer and not self._answer.done():
            self._answer.set_result(False)
        elif self._finished:
            self.dismiss(None)


@dataclass
class Field:
    """
    One line of a form: a text box, or a choice from a short list.
    """

    name: str
    label: str
    value: str = ""
    placeholder: str = ""
    hint: str = ""
    options: list[tuple[str, str]] = field(default_factory=list)
    # A value to hide while it is typed: keys, tokens, passwords.
    secret: bool = False


# What a form's submit hook answers with: nothing, if it worked; a sentence
# for the form as a whole; or a sentence per field.
Verdict = str | dict[str, str] | None


class FormModal(ModalScreen[dict[str, str] | None]):
    """
    A form that is only closed by something valid.

    `check` gets the values and says what is wrong with them - it may go and
    ask GitHub, which is why it is async. The window stays open with the
    complaint shown where it applies, so a typo costs a correction and not
    the retyping of five fields.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        title: str,
        fields: list[Field],
        *,
        ok: str = "Save",
        check: Callable[[dict[str, str]], Awaitable[Verdict]] | None = None,
    ) -> None:
        super().__init__(classes="dialog")
        self.title_text = title
        self.fields = fields
        self.ok = ok
        self.check = check

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.title_text, classes="title")
            with VerticalScroll():
                for item in self.fields:
                    yield Label(item.label, classes="field-label")
                    if item.options:
                        yield Select(
                            item.options,
                            value=item.value or item.options[0][1],
                            allow_blank=False,
                            id=f"f-{item.name}",
                        )
                    else:
                        yield Input(
                            value=item.value,
                            placeholder=item.placeholder,
                            password=item.secret,
                            id=f"f-{item.name}",
                        )
                    if item.hint:
                        yield Static(item.hint, classes="hint")
                    yield Label("", id=f"e-{item.name}", classes="error hidden")
            yield Label("", id="form-error", classes="error hidden")
            with Horizontal(classes="buttons"):
                yield Button(self.ok, id="ok", variant="primary")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one(f"#f-{self.fields[0].name}").focus()

    def values(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for item in self.fields:
            widget = self.query_one(f"#f-{item.name}")
            value = widget.value if isinstance(widget, (Input, Select)) else ""
            found[item.name] = "" if value is Select.BLANK else str(value).strip()
        return found

    def show_errors(self, verdict: Verdict) -> bool:
        """
        Put the complaints where they apply. True if there were none.
        """

        def put(label: Label, message: str) -> None:
            label.update(message)
            label.set_class(not message, "hidden")

        for item in self.fields:
            put(self.query_one(f"#e-{item.name}", Label), "")
        form_error = self.query_one("#form-error", Label)
        put(form_error, "")
        if verdict is None:
            return True
        if isinstance(verdict, str):
            put(form_error, verdict)
        else:
            for name, message in verdict.items():
                put(self.query_one(f"#e-{name}", Label), message)
        return False

    async def submit(self) -> None:
        values = self.values()
        if self.check is None:
            self.dismiss(values)
            return
        buttons = self.query(Button)
        for button in buttons:
            button.disabled = True
        checking = self.query_one("#form-error", Label)
        checking.update("Checking...")
        checking.remove_class("hidden")
        try:
            verdict = await self.check(values)
        except ManagerError as err:
            verdict = str(err)
        finally:
            for button in buttons:
                button.disabled = False
        if self.show_errors(verdict):
            self.dismiss(values)

    @on(Button.Pressed, "#ok")
    async def ok_pressed(self) -> None:
        await self.submit()

    @on(Input.Submitted)
    async def enter_pressed(self) -> None:
        await self.submit()

    @on(Button.Pressed, "#cancel")
    def cancel_pressed(self) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class Versions(ModalScreen[Version | None]):
    """
    The versions a source can be installed at, newest first.
    """

    BINDINGS = [
        Binding("b", "commit", "Build a commit"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(
        self,
        source: Source,
        load: Callable[[], Awaitable[list[Version]]],
        commits: Callable[[], Awaitable[list[Version]]] | None = None,
        *,
        title: str = "",
    ) -> None:
        super().__init__(classes="dialog wide")
        self.source = source
        self.load = load
        # How to list commits, if this window may offer to build one.
        self.commits = commits
        self.heading = title or f"Versions of {self.source.label}"
        self.versions: list[Version] = []

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(self.heading, classes="title")
            yield Label("Looking...", id="status")
            yield DataTable(id="versions", cursor_type="row", zebra_stripes=True)
            yield Static(
                "Enter installs the highlighted version."
                + (" b picks a commit to build." if self.commits else ""),
                classes="hint",
            )
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Version", "Kind", "Date", "Note")
        table.display = False
        self.run_worker(self.fill(), exclusive=True)

    async def fill(self) -> None:
        status = self.query_one("#status", Label)
        try:
            self.versions = await self.load()
        except ManagerError as err:
            status.update(f"[b]Could not list versions:[/b] {err}")
            status.add_class("error")
            return
        status.display = False
        table = self.query_one(DataTable)
        for version in self.versions:
            notes = [
                part
                for part in (
                    "pre-release" if version.prerelease else "",
                    version.asset.name if version.asset else "",
                    version.note,
                )
                if part
            ]
            table.add_row(
                version.label,
                version.kind,
                version.published[:10],
                ", ".join(notes),
                key=version.ref,
            )
        table.display = True
        table.focus()

    @on(DataTable.RowSelected)
    def chosen(self, event: DataTable.RowSelected) -> None:
        ref = event.row_key.value
        self.dismiss(next((v for v in self.versions if v.ref == ref), None))

    @work
    async def action_commit(self) -> None:
        """
        Choose a commit to build - one no release or tag names.
        """
        if self.commits is None:
            return
        commits = self.commits
        chosen = await self.app.push_screen_wait(
            Versions(
                self.source,
                commits,
                title=f"Commits of {self.source.label}: Enter builds one",
            )
        )
        if chosen is not None:
            self.dismiss(chosen)

    def action_back(self) -> None:
        self.dismiss(None)


@dataclass
class Pick:
    """
    A source and the version of it that was chosen to install.
    """

    source: Source
    version: Version


@dataclass
class ProgramPick:
    """
    A program chosen from a catalog.
    """

    source: Source
    catalog: catalogs.Catalog
    app: catalogs.CatalogApp


SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASS", re.IGNORECASE)


class CatalogBrowser(ModalScreen[ProgramPick | None]):
    """
    The programs a catalog holds, filterable, with a card for the one under
    the cursor.

    A catalog can hold dozens, so typing narrows the list at once instead of
    leaving a person to scroll. The arrows move through the list without
    leaving the box, and Enter takes the highlighted program, as in any
    launcher: type, arrow, Enter.
    """

    BINDINGS = [
        Binding("escape", "back", "Back"),
        Binding("down", "move(1)", "Next", show=False),
        Binding("up", "move(-1)", "Previous", show=False),
    ]

    def __init__(self, source: Source) -> None:
        super().__init__(classes="dialog wide")
        self.source = source
        self.catalog: catalogs.Catalog | None = None
        self.shown: dict[str, catalogs.CatalogApp] = {}

    @property
    def manager(self) -> Manager:
        return self.app.manager  # type: ignore[attr-defined]

    def compose(self) -> ComposeResult:
        with Container():
            yield Label(f"Programs in {self.source.label}", classes="title")
            yield Label("Asking GitHub...", id="status")
            yield Input(placeholder="Filter by name, tag or author", id="filter")
            yield DataTable(id="programs", cursor_type="row", zebra_stripes=True)
            yield Static("", id="about", classes="hint")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Name", "By", "Tags", "State")
        for hidden in ("#filter", "#programs", "#about"):
            self.query_one(hidden).display = False
        self.run_worker(self.fill(), exclusive=True)

    async def fill(self) -> None:
        status = self.query_one("#status", Label)
        try:
            self.catalog = await self.manager.catalog(self.source)
        except ManagerError as err:
            status.update(f"Could not read the catalog: {err}")
            status.add_class("error")
            return
        note = f"{len(self.catalog.apps)} programs"
        if self.catalog.problems:
            note += f" ({len(self.catalog.problems)} could not be read)"
        status.update(note + f" at {self.catalog.commit[:7]}")
        for shown in ("#filter", "#programs", "#about"):
            self.query_one(shown).display = True
        self.rebuild()
        self.query_one("#filter", Input).focus()

    def state_of(self, app: catalogs.CatalogApp) -> str:
        stamp = self.manager.programs.installed().get(app.slug)
        if stamp is None:
            return ""
        if stamp.repo != self.source.repo:
            return f"from {stamp.repo}"
        return "update" if needs_update(stamp, app) else "installed"

    def rebuild(self) -> None:
        if self.catalog is None:
            return
        words = self.query_one("#filter", Input).value.lower().split()
        table = self.query_one(DataTable)
        table.clear()
        self.shown = {}
        for app in self.catalog.apps:
            haystack = " ".join(
                (
                    app.slug,
                    app.name,
                    app.manifest.author,
                    app.manifest.description,
                    " ".join(app.manifest.tags),
                )
            ).lower()
            if all(word in haystack for word in words):
                self.shown[app.slug] = app
                table.add_row(
                    app.name,
                    app.manifest.author,
                    ", ".join(app.manifest.tags),
                    self.state_of(app),
                    key=app.slug,
                )
        self.describe()

    def current(self) -> catalogs.CatalogApp | None:
        table = self.query_one(DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return self.shown.get(key or "")

    def describe(self) -> None:
        about = self.query_one("#about", Static)
        app = self.current()
        if app is None:
            about.update("Nothing matches." if self.catalog else "")
            return
        lines = [app.manifest.description or "(no description)"]
        facts = [f"{max(app.size // 1024, 1)} KiB"]
        facts.append("installs packages" if app.needs_packages else "needs no packages")
        if app.env_template:
            facts.append("has settings")
        if app.manifest.upstream:
            facts.append(app.manifest.upstream)
        lines.append(" · ".join(facts))
        about.update("\n".join(lines))

    @on(Input.Changed, "#filter")
    def filtered(self) -> None:
        self.rebuild()

    @on(Input.Submitted, "#filter")
    def take_on_enter(self) -> None:
        self.chosen()

    def action_move(self, step: int) -> None:
        table = self.query_one(DataTable)
        if step > 0:
            table.action_cursor_down()
        else:
            table.action_cursor_up()

    @on(DataTable.RowHighlighted)
    def highlighted(self) -> None:
        self.describe()

    @on(DataTable.RowSelected)
    def chosen(self) -> None:
        app = self.current()
        if app is not None and self.catalog is not None:
            self.dismiss(ProgramPick(self.source, self.catalog, app))

    def action_back(self) -> None:
        self.dismiss(None)


async def ask_for_source(app: App) -> bool:
    """
    Ask where a source is - nothing more than that - and add it. True if one
    was added.

    What kind of thing it is (a catalog of programs, an app with releases, an
    app to build) is the manager's to find out, not the person's to say.
    """
    manager: Manager = app.manager  # type: ignore[attr-defined]

    async def check(values: dict[str, str]) -> Verdict:
        await manager.add_repo(values["repo"])
        return None

    added = await app.push_screen_wait(
        FormModal(
            "Add a source",
            [
                Field(
                    "repo",
                    "GitHub repository or folder",
                    placeholder="owner/name  or  ~/projects/my-app",
                    hint="A name or a pasted link for GitHub, a path for a folder "
                    "on this computer. What it offers shows up in the list as "
                    "not installed.",
                )
            ],
            ok="Add",
            check=check,
        )
    )
    return added is not None


class Sources(ModalScreen[Pick | ProgramPick | None]):
    """
    The places applications come from, and the way to install from them.
    """

    BINDINGS = [
        Binding("a", "add", "Add source"),
        Binding("A", "add_with_options", "With options"),
        Binding("p", "add_catalog", "Catalog on a branch", show=False),
        Binding("x", "remove", "Remove"),
        Binding("escape", "back", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__(classes="dialog wide")

    def compose(self) -> ComposeResult:
        with Container():
            yield Label("Sources", classes="title")
            yield DataTable(id="sources", cursor_type="row", zebra_stripes=True)
            yield Static("", id="empty", classes="hint")
            yield Static(
                "Enter picks what to install. A source is a GitHub repository: "
                "a catalog of programs, or an app's releases or source.",
                classes="hint",
            )
        yield Footer()

    @property
    def manager(self) -> Manager:
        return self.app.manager  # type: ignore[attr-defined]

    def on_mount(self) -> None:
        self.query_one(DataTable).add_columns(
            "Name", "Repository or folder", "Install from", "In it"
        )
        self.reload()

    def reload(self) -> None:
        table = self.query_one(DataTable)
        table.clear()
        sources = self.manager.store.config.sources
        for source in sources:
            table.add_row(
                source.label,
                source.origin,
                source.where_from,
                source.subdir or "",
                key=f"{source.repo}|{source.subdir}",
            )
        empty = self.query_one("#empty", Static)
        empty.update("" if sources else "No sources yet. Press a and type owner/name.")
        table.focus()

    def current(self) -> Source | None:
        table = self.query_one(DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return next(
            (
                s
                for s in self.manager.store.config.sources
                if f"{s.repo}|{s.subdir}" == key
            ),
            None,
        )

    @on(DataTable.RowSelected)
    @work
    async def pick(self) -> None:
        source = self.current()
        if source is None:
            return
        if source.kind == "catalog":
            program = await self.app.push_screen_wait(CatalogBrowser(source))
            if program is not None:
                self.dismiss(program)
            return
        version = await self.app.push_screen_wait(
            Versions(
                source,
                lambda: self.manager.versions(source),
                lambda: self.manager.commits(source),
            )
        )
        if version is not None:
            self.dismiss(Pick(source, version))

    @work
    async def action_add(self) -> None:
        if await ask_for_source(self.app):
            self.reload()

    @work
    async def action_add_with_options(self) -> None:
        async def check(values: dict[str, str]) -> Verdict:
            repo = values["repo"]
            if not REPO.match(repo):
                return {"repo": "use the form owner/name, as in github.com/owner/name"}
            if ".." in values["subdir"] or ".." in values["manifest"]:
                return "paths inside the repository cannot go up with .."
            source = Source(
                repo=repo,
                mode=values["mode"],  # type: ignore[arg-type]
                manifest=values["manifest"],
                asset=values["asset"] or "*.tgz",
                subdir=values["subdir"].strip("/"),
            )
            await self.manager.add_source(source)
            return None

        added = await self.app.push_screen_wait(
            FormModal(
                "Add an app source, with options",
                [
                    Field("repo", "GitHub repository", placeholder="owner/name"),
                    Field(
                        "mode",
                        "Install from",
                        value="release",
                        options=[
                            ("A release (nothing else to install)", "release"),
                            ("The source, built here (needs Node and pnpm)", "build"),
                        ],
                    ),
                    Field(
                        "asset",
                        "Release file",
                        value="*.tgz",
                        hint="Which file of a release is the package. Comma-separate patterns.",
                    ),
                    Field(
                        "subdir",
                        "Folder in the repository",
                        hint="Only if the repository holds several apps. Empty for the top.",
                    ),
                    Field(
                        "manifest",
                        "Manifest path",
                        hint="Only if it is not src/appmeta/manifest.json or appmeta/manifest.json.",
                    ),
                ],
                ok="Add",
                check=check,
            )
        )
        if added is not None:
            self.reload()

    @work
    async def action_add_catalog(self) -> None:
        async def check(values: dict[str, str]) -> Verdict:
            repo = values["repo"]
            if not REPO.match(repo):
                return {"repo": "use the form owner/name, as in github.com/owner/name"}
            await self.manager.add_source(
                Source(repo=repo, kind="catalog", branch=values["branch"])
            )
            return None

        added = await self.app.push_screen_wait(
            FormModal(
                "Add a catalog of programs",
                [
                    Field(
                        "repo",
                        "GitHub repository",
                        placeholder="owner/name",
                        hint="A repository with an apps/ folder of programs. The "
                        "community catalog is maxswinkels/busybar-apps.",
                    ),
                    Field("branch", "Branch", placeholder="main"),
                ],
                ok="Add",
                check=check,
            )
        )
        if added is not None:
            self.reload()

    @work
    async def action_remove(self) -> None:
        source = self.current()
        if source is None:
            return
        yes = await self.app.push_screen_wait(
            Confirm(
                f"Forget {source.label}?",
                "Apps already installed from it stay on the bar. Builds kept from it "
                "are deleted.",
                ok="Forget",
                variant="error",
            )
        )
        if yes:
            self.manager.forget_source(source)
            self.reload()

    def action_back(self) -> None:
        self.dismiss(None)
