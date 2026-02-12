from __future__ import annotations

import pkgutil
from collections.abc import Iterable
from importlib import import_module

from examples.remote.command_core import (
    CommandArgumentParser,
    CommandBase,
    CommandInput,
    CommandHandler,
    CommandRegistry as CoreCommandRegistry,
    register,
    register_command as core_register_command,
)
from examples.remote.commands.record_audio import InputCapture

__all__ = [
    "CommandArgumentParser",
    "CommandBase",
    "CommandInput",
    "CommandRegistry",
    "InputCapture",
    "discover_commands",
    "register",
    "register_command",
]


class CommandRegistry(CoreCommandRegistry):
    """
    Compatibility registry wrapper for legacy examples.remote.commands imports.

    Keeps the historical bool return type for ``handle()``.
    """

    async def handle(self, line: str) -> bool:
        """
        Parse and dispatch a command line.

        Returns True when a command was handled and False otherwise.
        """
        handled, _error = await super().handle(line)
        return handled


def register_command(
    registry: CommandRegistry,
    command: str | CommandBase,
    handler: CommandHandler | None = None,
) -> None:
    """
    Register command handlers with compatibility registry typing.
    """
    core_register_command(registry, command, handler)


def discover_commands(**deps: object) -> list[CommandBase]:
    """
    Discover command subclasses and build instances with dependencies.

    Imports all command modules to register subclasses before instantiation.
    """
    _import_commands()
    commands: list[CommandBase] = []
    for command_cls in _iter_command_classes():
        instance = command_cls.build(**deps)
        if instance is not None:
            commands.append(instance)
    return commands


def _import_commands() -> None:
    """
    Import all modules in this package to register command subclasses.
    """
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        import_module(f"{__name__}.{module.name}")


def _iter_command_classes() -> Iterable[type[CommandBase]]:
    """
    Yield concrete command subclasses registered in the current process.
    """
    for cls in CommandBase.__subclasses__():
        if cls is CommandBase:
            continue
        yield cls
