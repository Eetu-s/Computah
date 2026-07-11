"""Microphone listener: transcribe speech from a mic and POST each completed
sentence to another service.

Moonshine does its own voice-activity detection and emits a ``LineCompleted``
event when an utterance ends, so we post one whole sentence at a time — no
manual silence timer needed.

Usage:
    python -m app.listen                     # print sentences to the console
    POST_URL=http://consumer:9000/ingest python -m app.listen

Requires a microphone. In Docker, pass the host sound devices through
(see the ``mic`` service in docker-compose.yml).
"""

from __future__ import annotations

import os
import sys
import time

import requests
from moonshine_voice import MicTranscriber, TranscriptEventListener

from .core import DEFAULT_MODEL, resolve_model

# Where to POST completed sentences. If unset, sentences are only printed.
POST_URL = os.environ.get("POST_URL")

# Optional: pick a specific input device by index (see `python -m sounddevice`).
_MIC_DEVICE = os.environ.get("MOONSHINE_MIC_DEVICE")
MIC_DEVICE = int(_MIC_DEVICE) if _MIC_DEVICE not in (None, "") else None


class PostingListener(TranscriptEventListener):
    """Prints each completed sentence and (optionally) POSTs it to POST_URL."""

    def __init__(self, url: str | None) -> None:
        self.url = url
        self.session = requests.Session()

    def on_line_completed(self, event) -> None:
        text = event.line.text.strip()
        if not text:
            return

        print(f"> {text}", flush=True)

        if not self.url:
            return

        payload = {
            "text": text,
            "start_time": event.line.start_time,
            "duration": event.line.duration,
            "model": DEFAULT_MODEL,
        }
        try:
            resp = self.session.post(self.url, json=payload, timeout=5)
            resp.raise_for_status()
        except requests.RequestException as exc:
            print(f"POST to {self.url} failed: {exc}", file=sys.stderr)


def main() -> int:
    model_path, model_arch = resolve_model()

    mic = MicTranscriber(
        model_path=model_path,
        model_arch=model_arch,
        device=MIC_DEVICE,
    )
    mic.add_listener(PostingListener(POST_URL))

    target = POST_URL or "(console only — set POST_URL to forward)"
    print(f"Listening on the microphone. Posting sentences to: {target}", file=sys.stderr)
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
