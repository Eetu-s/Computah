"""Tool registry.

To add a tool: drop a module in this package and decorate a function with
@tool(...). It is discovered automatically at import — nothing else to edit.

    @tool(
        "set_volume",
        "Change the TV volume.",
        {"level": {"type": "integer", "description": "0-100"}},
        required=["level"],
    )
    def set_volume(cfg, level):
        ...

The handler's return value is logged as the outcome. Raise to signal failure;
the agent catches it and keeps listening.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger("computah.tools")

_REGISTRY: dict[str, "Tool"] = {}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict[str, dict]
    required: list[str]
    handler: Callable[..., Any]

    def spec(self) -> dict:
        """This tool as an OpenAI-style function spec (what llama-server wants)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.properties,
                    "required": self.required,
                },
            },
        }


def tool(name: str, description: str, properties: dict | None = None, required=None):
    def decorate(fn: Callable[..., Any]) -> Callable[..., Any]:
        if name in _REGISTRY:
            raise ValueError(f"duplicate tool name: {name}")
        _REGISTRY[name] = Tool(
            name=name,
            description=description,
            properties=properties or {},
            required=list(required or []),
            handler=fn,
        )
        return fn

    return decorate


def load() -> None:
    """Import every module in this package so their @tool calls run."""
    for mod in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{mod.name}")
    log.debug("registered tools: %s", ", ".join(sorted(_REGISTRY)))


def specs() -> list[dict]:
    return [t.spec() for t in _REGISTRY.values()]


def describe() -> str:
    """One line per tool, for the system prompt."""
    return "\n".join(f"- {t.name}: {t.description}" for t in _REGISTRY.values())


def dispatch(cfg, name: str, arguments: dict) -> Any:
    """Run a tool the model picked. Raises KeyError if it hallucinated the name."""
    if name not in _REGISTRY:
        raise KeyError(f"unknown tool {name!r} (have: {', '.join(sorted(_REGISTRY))})")

    known = _REGISTRY[name].properties
    extra = set(arguments) - set(known)
    if extra:
        # Small models like to invent arguments; drop them rather than crash.
        log.warning("dropping unexpected args for %s: %s", name, ", ".join(sorted(extra)))
        arguments = {k: v for k, v in arguments.items() if k in known}

    return _REGISTRY[name].handler(cfg, **arguments)
