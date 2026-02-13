from __future__ import annotations

import pkgutil
from collections.abc import Iterable
from importlib import import_module

from examples.remote.command_core import (
    CommandBase,
)
from examples.remote.commands.record_audio import InputCapture

__all__ = [
    "InputCapture",
    "discover_commands",
]


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
