"""Command registry for computah-engine.

Each command is a small, self-contained module in this package that registers
a handler with the ``@command("name")`` decorator. To add a new command, drop
a new file in this folder — it's picked up automatically at startup; no changes
to the server needed.

A handler receives the request payload (a dict) and returns a dict describing
the result.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Callable, Dict

# Maps a command name (e.g. "turn-on-led") to its handler.
CommandHandler = Callable[[dict], dict]
COMMANDS: Dict[str, CommandHandler] = {}


def command(name: str) -> Callable[[CommandHandler], CommandHandler]:
    """Register ``func`` as the handler for command ``name``."""

    def decorator(func: CommandHandler) -> CommandHandler:
        COMMANDS[name] = func
        return func

    return decorator


def load_commands() -> Dict[str, CommandHandler]:
    """Import every command module in this package so handlers register."""
    for module in pkgutil.iter_modules(__path__):
        if module.name.startswith("_"):
            continue
        importlib.import_module(f"{__name__}.{module.name}")
    return COMMANDS
