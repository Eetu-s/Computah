"""Built-in tools that aren't tied to any particular device."""
from __future__ import annotations

from . import tool


@tool(
    "no_action",
    "Do nothing. Use this when the speech was not a command addressed to you — "
    "background conversation, TV audio, or an instruction you have no tool for.",
    {
        "reason": {
            "type": "string",
            "description": "Briefly, what you heard and why it needs no action.",
        }
    },
)
def no_action(cfg, reason: str = ""):
    return f"ignored: {reason}" if reason else "ignored"
