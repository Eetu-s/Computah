"""Command: toggle the TV between on and standby.

Forwards to computah-cast's /power endpoint. Reached at
``POST /commands/tv-power``.
"""

from __future__ import annotations

from . import command
from ._cast_client import cast_post


@command("tv-power")
def tv_power(params: dict) -> dict:
    print("Executing command: toggle TV power", flush=True)
    return {"command": "tv-power", "status": "ok", "cast": cast_post("/power")}
