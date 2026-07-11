"""Command: press a key on the TV remote.

Forwards to computah-cast's /key endpoint. Reached at
``POST /commands/tv-key`` with body ``{"key": "KEY_VOLUMEUP"}``.
"""

from __future__ import annotations

from . import command
from ._cast_client import cast_post


@command("tv-key")
def tv_key(params: dict) -> dict:
    key = str(params.get("key", "")).strip().upper()
    if not key:
        raise ValueError("tv-key requires a 'key' parameter")
    if not key.startswith("KEY_"):
        key = f"KEY_{key}"

    print(f"Executing command: TV key {key}", flush=True)
    return {
        "command": "tv-key",
        "status": "ok",
        "key": key,
        "cast": cast_post("/key", {"key": key}),
    }
