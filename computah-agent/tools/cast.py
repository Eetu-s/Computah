"""Tools for the Hisense VIDAA TV, routed through computah-engine.

The engine forwards these to computah-cast (../computah-cast). Going through the
engine keeps STT and the LLM on one unified command path.
"""
from __future__ import annotations

import logging

import requests

from . import tool

log = logging.getLogger("computah.tools.cast")

# The subset of Hisense remote keys worth exposing to speech. Constraining the
# enum keeps a small model from inventing key names that the TV would reject.
KEYS = [
    "KEY_POWER",
    "KEY_HOME",
    "KEY_BACK",
    "KEY_OK",
    "KEY_UP",
    "KEY_DOWN",
    "KEY_LEFT",
    "KEY_RIGHT",
    "KEY_VOLUMEUP",
    "KEY_VOLUMEDOWN",
    "KEY_MUTE",
    "KEY_PLAY",
    "KEY_PAUSE",
    "KEY_STOP",
]


def _run(cfg, command: str, **kwargs):
    """Trigger an engine command (which forwards to computah-cast)."""
    resp = requests.post(
        f"{cfg.engine_url}/{command}", timeout=cfg.engine_timeout, **kwargs
    )
    resp.raise_for_status()
    return resp.json()


@tool(
    "cast_image",
    "Show the currently hosted picture on the TV, waking the TV first if it is "
    "off. Use for things like 'put the picture up', 'show it on the TV', 'cast it'.",
)
def cast_image(cfg):
    return _run(cfg, "cast-image")


@tool(
    "tv_power",
    "Toggle the TV between on and standby. Use for 'turn the TV on/off'.",
)
def tv_power(cfg):
    return _run(cfg, "tv-power")


@tool(
    "tv_key",
    "Press a button on the TV remote. Use for volume, muting, navigation and "
    "playback control.",
    {
        "key": {
            "type": "string",
            "enum": KEYS,
            # Spelling out the direction words matters: a 4B model will happily
            # answer "turn it up" with KEY_VOLUMEDOWN given only the enum names.
            "description": (
                "Which remote key to press. KEY_VOLUMEUP = louder / turn it up / "
                "raise the volume. KEY_VOLUMEDOWN = quieter / turn it down / "
                "lower the volume. KEY_MUTE = silence it. KEY_PLAY / KEY_PAUSE / "
                "KEY_STOP control playback. KEY_UP / KEY_DOWN / KEY_LEFT / "
                "KEY_RIGHT / KEY_OK / KEY_BACK / KEY_HOME navigate menus."
            ),
        }
    },
    required=["key"],
)
def tv_key(cfg, key: str):
    key = key.strip().upper()
    if not key.startswith("KEY_"):
        key = f"KEY_{key}"
    if key not in KEYS:
        raise ValueError(f"unsupported key {key!r}")
    return _run(cfg, "tv-key", json={"key": key})
