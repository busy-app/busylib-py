"""
Manage the applications on a BUSY Bar, and the programs that go with it.

    python -m examples.apps.main                 # find a bar on the network
    python -m examples.apps.main 192.168.1.20    # or say which
    python -m examples.apps.main --offline       # no bar: sources and programs only

Needs `textual`. Installing from a release needs nothing else; building from
source needs Node.js and pnpm.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from busylib.client import AsyncBusyBar

from examples.shared.discovery import resolve_connection

from .bar import Bar
from .github import Cache, GitHub
from .launcher import Launcher
from .manager import Manager
from .store import Store


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="apps",
        description=(
            "Install, launch and remove the JavaScript apps on a BUSY Bar, from "
            "GitHub releases or built from source, and start programs from this "
            "computer alongside them."
        ),
    )
    parser.add_argument(
        "addr_positional", nargs="?", default=None, help="Device address"
    )
    parser.add_argument("--addr", default=None, help="Device address")
    parser.add_argument("--token", default=None, help="Device access key")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not connect to a bar: manage sources and programs only",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Where sources and programs are kept (default: your user settings folder)",
    )
    parser.add_argument("--log-level", default="INFO", help="Level of the log file")
    args = parser.parse_args(argv)
    if args.addr is None:
        args.addr = args.addr_positional
    return args


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    try:
        from .tui import AppsManager
    except ModuleNotFoundError as err:
        if err.name and err.name.split(".")[0] == "textual":
            print(
                "This example needs the 'textual' package:\n"
                f"    {sys.executable} -m pip install textual"
            )
            sys.exit(1)
        raise

    store = Store(args.config)
    store.load()

    # The terminal belongs to the interface while it runs; anything logged
    # to it would be drawn over the screen. The file is where to look when
    # something misbehaves.
    store.dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=store.dir / "manager.log",
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    bar: Bar | None = None
    close = None
    address = ""
    if not args.offline:
        addr, token = args.addr, args.token
        if addr is None:
            addr, token = resolve_connection(token)
        # Compatibility checks are off because the apps calls are marked
        # experimental and would warn on every one; the bar's own answers
        # (a 404 on firmware without apps) are handled where they happen.
        client = AsyncBusyBar(
            addr=addr, token=token, compatibility_mode="none", timeout=15.0
        )
        bar, close, address = Bar(client, addr), client.aclose, addr

    # What GitHub already told us is kept between runs, so opening a catalog
    # on every start costs two answers of "unchanged" and not forty downloads.
    github = GitHub(cache=Cache(store.dir / "http-cache.json"))
    # `{host}` in a program's command is the bar this manager is connected to.
    launcher = Launcher(store.dir / "logs", host=address)
    manager = Manager(store, github, launcher, bar)
    try:
        AppsManager(manager, address, close).run()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
