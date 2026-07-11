"""Microphone listener: transcribe speech, match it to a command, and POST that
command to the engine.

Moonshine does its own voice-activity detection and emits a ``LineCompleted``
event when an utterance ends, so we look at one whole sentence at a time — no
manual silence timer needed. If the sentence contains a known phrase, we POST
to the engine's matching command endpoint (``ENGINE_URL/<command>``).

Usage:
    python listen.py
    ENGINE_URL=http://computah-engine:9000/commands python listen.py

Requires a microphone. In Docker, pass the host sound devices through
(see the ``mic`` service in docker-compose.yml).
"""

from __future__ import annotations

import os
import sys
import time

import requests
from moonshine_voice import MicTranscriber, TranscriptEventListener

from core import resolve_model

# Base URL of the engine's command endpoints; a command name is appended.
ENGINE_URL = os.environ.get("ENGINE_URL", "http://computah-engine:9000/commands").rstrip("/")

# Phrase -> command name. If a recognized sentence contains the phrase
# (case-insensitive), the matching command is triggered. Add more rules here.
# Commands run in the engine; device commands (e.g. cast-image) are forwarded
# by the engine to computah-cast — same unified path the LLM agent uses.
COMMAND_PHRASES = {
    "led on": "turn-on-led",
    "show the picture": "cast-image",
    "turn on the tv": "tv-power",
}

# Optional: pick a specific input device by index (see `python -m sounddevice`).
_MIC_DEVICE = os.environ.get("MOONSHINE_MIC_DEVICE")
MIC_DEVICE = int(_MIC_DEVICE) if _MIC_DEVICE not in (None, "") else None


def match_command(text: str) -> str | None:
    """Return the command name for the first phrase found in ``text``, or None."""
    lowered = text.lower()
    for phrase, command in COMMAND_PHRASES.items():
        if phrase in lowered:
            return command
    return None


class CommandListener(TranscriptEventListener):
    """Prints each completed sentence and POSTs matched commands to the engine."""

    def __init__(self, engine_url: str) -> None:
        self.engine_url = engine_url
        self.session = requests.Session()

    def on_line_completed(self, event) -> None:
        text = event.line.text.strip()
        if not text:
            return

        print(f"> {text}", flush=True)

        command = match_command(text)
        if command is None:
            return

        url = f"{self.engine_url}/{command}"
        payload = {"text": text}
        try:
            resp = self.session.post(url, json=payload, timeout=5)
            resp.raise_for_status()
            print(f"  → triggered '{command}'", flush=True)
        except requests.RequestException as exc:
            print(f"POST to {url} failed: {exc}", file=sys.stderr)


def main() -> int:
    model_path, model_arch = resolve_model()

    mic = MicTranscriber(
        model_path=model_path,
        model_arch=model_arch,
        device=MIC_DEVICE,
    )
    mic.add_listener(CommandListener(ENGINE_URL))

    print(f"Listening on the microphone. Commands go to: {ENGINE_URL}/<command>", file=sys.stderr)
    print(f"Known phrases: {', '.join(COMMAND_PHRASES)}", file=sys.stderr)
    print("Press Ctrl+C to stop.", file=sys.stderr)

    mic.start()
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...", file=sys.stderr)
    finally:
        mic.stop()
        mic.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
