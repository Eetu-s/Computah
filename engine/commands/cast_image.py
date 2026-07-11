"""Command: show the currently hosted picture on the TV.

Forwards to computah-cast's /cast endpoint. Reached at
``POST /commands/cast-image``.
"""

from __future__ import annotations

from . import command
from ._cast_client import cast_post


@command("cast-image")
def cast_image(params: dict) -> dict:
    print("Executing command: cast image to TV", flush=True)
    return {"command": "cast-image", "status": "ok", "cast": cast_post("/cast")}
