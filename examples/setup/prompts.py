from __future__ import annotations

import getpass
from typing import Protocol, runtime_checkable


class SetupCancelled(Exception):
    """
    Raised to skip the current step and move on to the next one.
    """


class SetupAborted(Exception):
    """
    Raised to leave the wizard entirely.

    Kept separate from `SetupCancelled` so that Ctrl+C or Escape quits
    instead of skipping one step and immediately prompting for the next.
    """


@runtime_checkable
class Prompt(Protocol):
    """
    Input/output surface a setup step needs.

    Implemented once for a plain terminal and once for the `remote` TUI, so
    the steps themselves never touch stdin directly and stay testable.
    """

    def info(self, message: str) -> None:
        """
        Show a progress or result line to the user.
        """
        ...

    async def text(self, message: str, *, default: str | None = None) -> str:
        """
        Ask for a line of text, raising `SetupCancelled` if aborted.
        """
        ...

    async def secret(self, message: str) -> str:
        """
        Ask for a value that must not be echoed, such as a password.
        """
        ...

    async def confirm(self, message: str, *, default: bool = True) -> bool:
        """
        Ask a yes/no question.
        """
        ...

    async def choose(self, message: str, options: list[str]) -> int:
        """
        Ask the user to pick one of `options`, returning its index.
        """
        ...


class TerminalPrompt:
    """
    Plain-stdin prompt used when the wizard runs on its own.
    """

    def info(self, message: str) -> None:
        """
        Print a line to stdout.
        """
        print(message)

    async def text(self, message: str, *, default: str | None = None) -> str:
        """
        Read a line, falling back to `default` when the input is empty.
        """
        suffix = f" [{default}]" if default else ""
        try:
            value = input(f"{message}{suffix}: ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise SetupAborted from exc
        if not value and default is not None:
            return default
        return value

    async def secret(self, message: str) -> str:
        """
        Read a line without echoing it.
        """
        try:
            return getpass.getpass(f"{message}: ").strip()
        except (EOFError, KeyboardInterrupt) as exc:
            raise SetupAborted from exc

    async def confirm(self, message: str, *, default: bool = True) -> bool:
        """
        Read a yes/no answer, defaulting on empty input.
        """
        hint = "Y/n" if default else "y/N"
        try:
            answer = input(f"{message} [{hint}]: ").strip().lower()
        except (EOFError, KeyboardInterrupt) as exc:
            raise SetupAborted from exc
        if not answer:
            return default
        return answer in ("y", "yes")

    async def choose(self, message: str, options: list[str]) -> int:
        """
        Print a numbered menu and read a valid selection.
        """
        if not options:
            raise ValueError("choose() requires at least one option")
        print(message)
        for index, option in enumerate(options, start=1):
            print(f"  {index}. {option}")
        while True:
            try:
                raw = input(f"Select [1-{len(options)}]: ").strip()
            except (EOFError, KeyboardInterrupt) as exc:
                raise SetupCancelled from exc
            if raw.isdigit() and 1 <= int(raw) <= len(options):
                return int(raw) - 1
            print(f"Enter a number between 1 and {len(options)}.")
