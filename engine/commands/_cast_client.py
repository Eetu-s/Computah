"""Helper for forwarding a command to computah-cast (the TV service).

Dependency-free (stdlib urllib) so the engine image needs no pip install.
The leading underscore keeps this module out of the command auto-discovery in
``load_commands`` — it's a helper, not a command.
"""

from __future__ import annotations

import json
import os
import urllib.request

# Base URL of computah-cast. With host networking it's on 127.0.0.1:8000.
CAST_URL = os.environ.get("CAST_URL", "http://computah-cast:8000").rstrip("/")
CAST_TIMEOUT = int(os.environ.get("CAST_TIMEOUT", "30"))


def cast_post(path: str, payload: dict | None = None) -> dict:
    """POST to computah-cast at ``CAST_URL + path`` and return its JSON reply."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{CAST_URL}{path}",
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=CAST_TIMEOUT) as resp:
        body = resp.read().decode()
    try:
        return json.loads(body) if body else {}
    except json.JSONDecodeError:
        return {"raw": body}
