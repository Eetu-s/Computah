"""Command-line interface: transcribe one or more audio files.

Usage:
    python -m app.transcribe recording.wav
    python -m app.transcribe --model moonshine/base a.wav b.flac
"""

from __future__ import annotations

import argparse
import sys
import time

from .core import transcribe


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="app.transcribe",
        description="Transcribe audio files with Moonshine.",
    )
    parser.add_argument("audio", nargs="+", help="Path(s) to audio file(s).")
    parser.add_argument(
        "--timing",
        action="store_true",
        help="Print how long transcription took (to stderr).",
    )
    args = parser.parse_args(argv)

    exit_code = 0
    for path in args.audio:
        try:
            start = time.perf_counter()
            text = transcribe(path)
            elapsed = time.perf_counter() - start
        except Exception as exc:  # noqa: BLE001 - surface a clean CLI error
            print(f"error: {path}: {exc}", file=sys.stderr)
            exit_code = 1
            continue

        if len(args.audio) > 1:
            print(f"{path}: {text}")
        else:
            print(text)

        if args.timing:
            print(f"  ({elapsed:.2f}s)", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
