from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from apps_support import CatalogNet, manifest_bytes

from examples.apps import catalog as catalogs
from examples.apps.github import GitHub, Reply
from examples.apps.model import ManagerError, Source
from examples.apps.programs import STAMP, Programs, needs_update

SOURCE = Source(repo="busy-app/programs", kind="catalog")


def _files(**extra: bytes) -> dict[str, bytes]:
    return {
        "app.py": b"print('v1')\n",
        "manifest.yaml": manifest_bytes("Clock"),
        **extra,
    }


class _Runs:
    """
    Stands in for pip and venv: records what was run, and can fail.
    """

    def __init__(self, fail_on: str = "") -> None:
        self.commands: list[list[str]] = []
        self.fail_on = fail_on

    def __call__(self, argv: list[str], cwd: Path) -> tuple[int, str]:
        self.commands.append(argv)
        if self.fail_on and self.fail_on in argv:
            return 1, "ERROR: no matching distribution\nfor requests"
        if argv[1:3] == ["-m", "venv"]:
            interpreter = Path(argv[3]) / (
                "Scripts/python.exe" if sys.platform == "win32" else "bin/python"
            )
            interpreter.parent.mkdir(parents=True)
            interpreter.write_text("")
        return 0, ""

    def verbs(self) -> list[str]:
        return ["venv" if c[1:3] == ["-m", "venv"] else "pip" for c in self.commands]


def _setup(tmp_path: Path, programs: dict[str, dict[str, bytes]], run=None):
    net = CatalogNet(programs)
    github = GitHub(net, token="")
    installer = Programs(tmp_path / "programs", github, run=run or _Runs())
    return net, github, installer, github.catalog(SOURCE)


def test_an_install_puts_the_files_where_the_program_lives(tmp_path: Path) -> None:
    _, _, installer, catalog = _setup(tmp_path, {"clock": _files()})
    app = catalog.find("clock")
    assert app is not None
    said: list[str] = []

    stamp = installer.install(SOURCE, catalog, app, said.append)

    folder = tmp_path / "programs" / "clock"
    assert (folder / "app.py").read_bytes() == b"print('v1')\n"
    assert stamp.commit == "c0ffee" and stamp.repo == "busy-app/programs"
    assert set(stamp.files) == {"app.py", "manifest.yaml"}
    assert json.loads((folder / STAMP).read_text())["commit"] == "c0ffee"
    assert any("downloading 2 file(s)" in line for line in said)


def test_what_is_installed_is_listed_with_where_it_came_from(tmp_path: Path) -> None:
    _, _, installer, catalog = _setup(tmp_path, {"clock": _files()})
    installer.install(SOURCE, catalog, catalog.apps[0])
    (tmp_path / "programs" / "not-ours").mkdir()
    (tmp_path / "programs" / ".hidden").mkdir()

    assert list(installer.installed()) == ["clock"]


def test_a_program_with_no_packages_gets_no_environment(tmp_path: Path) -> None:
    run = _Runs()
    _, _, installer, catalog = _setup(tmp_path, {"clock": _files()}, run)

    installer.install(SOURCE, catalog, catalog.apps[0])

    assert run.commands == []


def test_a_program_with_packages_gets_its_own_environment_beside_it(
    tmp_path: Path,
) -> None:
    run = _Runs()
    _, _, installer, catalog = _setup(
        tmp_path, {"clock": _files(**{"requirements.txt": b"requests\n"})}, run
    )

    installer.install(SOURCE, catalog, catalog.apps[0])

    assert run.verbs() == ["venv", "pip"]
    assert (tmp_path / "programs" / ".venvs" / "clock").is_dir()
    assert not (tmp_path / "programs" / "clock" / ".venv").exists(), (
        "an environment cannot be moved, and replacing a folder moves it"
    )
    pip = run.commands[1]
    assert pip[1:3] == ["-m", "pip"] and pip[-2] == "-r"
    assert installer.venv_python("clock").exists()


def test_an_update_with_the_same_requirements_keeps_the_environment(
    tmp_path: Path,
) -> None:
    run = _Runs()
    net, github, installer, catalog = _setup(
        tmp_path, {"clock": _files(**{"requirements.txt": b"requests\n"})}, run
    )
    installer.install(SOURCE, catalog, catalog.apps[0])
    net.programs["clock"]["app.py"] = b"print('v2')\n"
    again = github.catalog(SOURCE)
    run.commands.clear()
    said: list[str] = []

    installer.install(SOURCE, again, again.apps[0], said.append)

    assert run.commands == []
    assert "packages unchanged" in said
    assert (tmp_path / "programs" / "clock" / "app.py").read_bytes() == b"print('v2')\n"


def test_changed_requirements_are_installed_into_the_environment_it_has(
    tmp_path: Path,
) -> None:
    run = _Runs()
    net, github, installer, catalog = _setup(
        tmp_path, {"clock": _files(**{"requirements.txt": b"requests\n"})}, run
    )
    installer.install(SOURCE, catalog, catalog.apps[0])
    net.programs["clock"]["requirements.txt"] = b"requests\nrich\n"
    again = github.catalog(SOURCE)
    run.commands.clear()

    installer.install(SOURCE, again, again.apps[0])

    assert run.verbs() == ["pip"], "no second environment"


def test_packages_that_will_not_install_leave_nothing_half_done(tmp_path: Path) -> None:
    run = _Runs(fail_on="pip")
    _, _, installer, catalog = _setup(
        tmp_path, {"clock": _files(**{"requirements.txt": b"nonsense\n"})}, run
    )

    with pytest.raises(
        ManagerError, match=r"(?s)installing its packages failed.*no matching"
    ):
        installer.install(SOURCE, catalog, catalog.apps[0])

    root = tmp_path / "programs"
    assert not (root / "clock").exists()
    assert not (root / ".venvs" / "clock").exists()
    assert not [p for p in root.iterdir() if p.name.startswith(".staging")]


def test_a_failed_update_leaves_the_old_program_running(tmp_path: Path) -> None:
    run = _Runs()
    net, github, installer, catalog = _setup(
        tmp_path, {"clock": _files(**{"requirements.txt": b"requests\n"})}, run
    )
    installer.install(SOURCE, catalog, catalog.apps[0])
    net.programs["clock"]["app.py"] = b"print('v2')\n"
    net.programs["clock"]["requirements.txt"] = b"broken\n"
    again = github.catalog(SOURCE)
    run.fail_on = "pip"

    with pytest.raises(ManagerError):
        installer.install(SOURCE, again, again.apps[0])

    assert (tmp_path / "programs" / "clock" / "app.py").read_bytes() == b"print('v1')\n"


def test_a_file_that_is_not_the_one_listed_stops_the_install(tmp_path: Path) -> None:
    net, github, installer, catalog = _setup(tmp_path, {"clock": _files()})
    real = net.__call__

    def swapped(url: str, headers: dict[str, str], limit: int) -> Reply:
        if url.endswith("/apps/clock/app.py"):
            return Reply(200, b"import os; os.system('rm -rf ~')\n")
        return real(url, headers, limit)

    installer.github = GitHub(swapped, token="")

    with pytest.raises(ManagerError, match="not the file the listing described"):
        installer.install(SOURCE, catalog, catalog.apps[0])

    assert not (tmp_path / "programs" / "clock").exists()
    assert not [
        p for p in (tmp_path / "programs").iterdir() if p.name.startswith(".staging")
    ]


def test_an_update_replaces_the_folder_and_keeps_when_it_was_first_installed(
    tmp_path: Path,
) -> None:
    net, github, installer, catalog = _setup(
        tmp_path, {"clock": _files(**{"old_module.py": b"x"})}
    )
    first = installer.install(SOURCE, catalog, catalog.apps[0])
    del net.programs["clock"]["old_module.py"]
    net.programs["clock"]["app.py"] = b"print('v2')\n"
    again = github.catalog(SOURCE)

    second = installer.install(SOURCE, again, again.apps[0])

    folder = tmp_path / "programs" / "clock"
    assert not (folder / "old_module.py").exists(), "a file the program dropped is gone"
    assert second.installed_at == first.installed_at
    assert second.updated_at >= first.updated_at


def test_a_slug_from_another_repository_is_not_overwritten(tmp_path: Path) -> None:
    _, _, installer, catalog = _setup(tmp_path, {"clock": _files()})
    installer.install(SOURCE, catalog, catalog.apps[0])
    other = Source(repo="someone/else", kind="catalog")

    with pytest.raises(ManagerError, match="already installed from busy-app/programs"):
        installer.install(other, catalog, catalog.apps[0])


def test_a_folder_the_manager_did_not_make_is_not_overwritten(tmp_path: Path) -> None:
    _, _, installer, catalog = _setup(tmp_path, {"clock": _files()})
    mine = tmp_path / "programs" / "clock"
    mine.mkdir(parents=True)
    (mine / "precious.txt").write_text("x")

    with pytest.raises(ManagerError, match="was not installed by this manager"):
        installer.install(SOURCE, catalog, catalog.apps[0])

    assert (mine / "precious.txt").exists()


# What changed ------------------------------------------------------------------


def test_a_program_is_out_of_date_when_its_own_files_changed(tmp_path: Path) -> None:
    net, github, installer, catalog = _setup(tmp_path, {"clock": _files()})
    stamp = installer.install(SOURCE, catalog, catalog.apps[0])

    assert needs_update(stamp, catalog.apps[0]) is False

    net.programs["clock"]["app.py"] = b"print('v2')\n"
    assert needs_update(stamp, github.catalog(SOURCE).apps[0]) is True


def test_a_program_is_not_out_of_date_because_a_neighbour_changed(
    tmp_path: Path,
) -> None:
    """
    The catalog's commit moves when any program in it changes; one program's
    "update available" must not light up for all of them.
    """
    net, github, installer, catalog = _setup(
        tmp_path, {"clock": _files(), "weather": _files()}
    )
    clock = next(a for a in catalog.apps if a.slug == "clock")
    stamp = installer.install(SOURCE, catalog, clock)

    net.programs["weather"]["app.py"] = b"print('new weather')\n"
    newer = github.catalog(SOURCE)

    assert (
        needs_update(stamp, next(a for a in newer.apps if a.slug == "clock")) is False
    )


def test_a_file_added_or_dropped_upstream_is_an_update_too(tmp_path: Path) -> None:
    net, github, installer, catalog = _setup(tmp_path, {"clock": _files()})
    stamp = installer.install(SOURCE, catalog, catalog.apps[0])

    net.programs["clock"]["helper.py"] = b"x"

    assert needs_update(stamp, github.catalog(SOURCE).apps[0]) is True


# Before installing --------------------------------------------------------------


def test_the_plan_says_what_an_install_will_bring(tmp_path: Path) -> None:
    _, _, installer, catalog = _setup(
        tmp_path,
        {"clock": _files(**{"requirements.txt": b"# deps\nrequests>=2\n\nrich\n"})},
    )

    plan = installer.plan(SOURCE, catalog, catalog.apps[0])

    assert plan.files == 3
    assert plan.packages == ("requests>=2", "rich")
    assert plan.replaces is None
    assert plan.folder == tmp_path / "programs" / "clock"


def test_the_plan_says_what_it_would_replace(tmp_path: Path) -> None:
    _, _, installer, catalog = _setup(tmp_path, {"clock": _files()})
    installed = installer.install(SOURCE, catalog, catalog.apps[0])

    assert installer.plan(SOURCE, catalog, catalog.apps[0]).replaces == installed


def test_a_program_far_larger_than_programs_are_is_refused_in_the_plan(
    tmp_path: Path,
) -> None:
    _, _, installer, catalog = _setup(tmp_path, {"clock": _files()})
    huge = catalogs.CatalogApp(
        slug="clock",
        manifest=catalogs.Manifest(name="Clock"),
        files={"app.py": "a"},
        size=catalogs.MAX_INSTALL_BYTES + 1,
    )

    with pytest.raises(
        ManagerError, match="more than a program of this kind should be"
    ):
        installer.plan(SOURCE, catalog, huge)


# Removing ----------------------------------------------------------------------


def test_removing_takes_the_program_and_its_packages_and_nothing_else(
    tmp_path: Path,
) -> None:
    run = _Runs()
    _, _, installer, catalog = _setup(
        tmp_path,
        {"clock": _files(**{"requirements.txt": b"requests\n"}), "weather": _files()},
        run,
    )
    for app in catalog.apps:
        installer.install(SOURCE, catalog, app)

    installer.remove("clock")

    root = tmp_path / "programs"
    assert not (root / "clock").exists()
    assert not (root / ".venvs" / "clock").exists()
    assert (root / "weather" / "app.py").exists()


def test_a_folder_without_the_stamp_is_never_deleted(tmp_path: Path) -> None:
    root = tmp_path / "programs"
    (root / "mine").mkdir(parents=True)
    (root / "mine" / "work.txt").write_text("x")
    installer = Programs(root, GitHub(CatalogNet({}), token=""))

    with pytest.raises(ManagerError, match="left alone"):
        installer.remove("mine")

    assert (root / "mine" / "work.txt").exists()


@pytest.mark.skipif(
    sys.platform == "win32", reason="symlinks need privileges on Windows"
)
def test_a_link_is_never_followed_into_deleting_what_it_points_at(
    tmp_path: Path,
) -> None:
    precious = tmp_path / "precious"
    precious.mkdir()
    (precious / "keep.txt").write_text("x")
    (precious / STAMP).write_text("{}")
    root = tmp_path / "programs"
    root.mkdir()
    os.symlink(precious, root / "clock")
    installer = Programs(root, GitHub(CatalogNet({}), token=""))

    with pytest.raises(ManagerError, match="not a program this manager installed"):
        installer.remove("clock")

    assert (precious / "keep.txt").exists()


@pytest.mark.parametrize("name", ["../etc", "/abs", "a/b", "..", "", "UPPER", ".venvs"])
def test_a_name_that_is_not_a_slug_never_reaches_the_filesystem(
    tmp_path: Path, name: str
) -> None:
    installer = Programs(tmp_path / "programs", GitHub(CatalogNet({}), token=""))

    with pytest.raises(
        ManagerError, match="not a name a program can be installed under"
    ):
        installer.remove(name)


# The environment it reads -------------------------------------------------------


def test_the_variables_a_program_reads_come_from_its_own_template(
    tmp_path: Path,
) -> None:
    _, _, installer, catalog = _setup(
        tmp_path,
        {
            "clock": _files(
                **{".env.example": b"# Where you live\nCITY=Utrecht\nTOKEN=\n"}
            )
        },
    )
    installer.install(SOURCE, catalog, catalog.apps[0])

    spec = installer.env_spec("clock")

    assert [(v.key, v.example, v.help) for v in spec] == [
        ("CITY", "Utrecht", "Where you live"),
        ("TOKEN", "", ""),
    ]


def test_a_program_with_no_template_reads_nothing_we_know_of(tmp_path: Path) -> None:
    _, _, installer, catalog = _setup(tmp_path, {"clock": _files()})
    installer.install(SOURCE, catalog, catalog.apps[0])

    assert installer.env_spec("clock") == []
