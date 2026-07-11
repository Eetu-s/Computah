"""computah-agent: speech in, tool call out.

Listens to the microphone, hands each utterance to Gemma 4 as audio, and runs
whichever tool Gemma picks.

    python agent.py                    # listen to the mic
    python agent.py --file cmd.wav     # run one recording through (no mic needed)
    python agent.py --list-devices     # find the mic's index for MIC_DEVICE
"""
from __future__ import annotations

import argparse
import logging
import sys

import requests

import audio
import config
import tools
from llm import Gemma

log = logging.getLogger("computah.agent")


def handle(cfg, gemma: Gemma, wav: bytes) -> None:
    """One utterance: ask Gemma, run what it chose."""
    try:
        call = gemma.decide(wav)
    except requests.RequestException as exc:
        log.error("Gemma request failed: %s", exc)
        return

    if call is None:
        return

    if call.name == "no_action":
        log.info("no_action (%s)", call.arguments.get("reason", ""))
        return

    args = call.arguments
    pretty = ", ".join(f"{k}={v!r}" for k, v in args.items())
    log.info("tool: %s(%s)", call.name, pretty)

    if cfg.dry_run:
        log.info("DRY_RUN — not executing")
        return

    try:
        result = tools.dispatch(cfg, call.name, args)
    except KeyError as exc:
        log.error("%s", exc)
    except requests.RequestException as exc:
        log.error("%s failed: %s", call.name, exc)
    except Exception as exc:  # noqa: BLE001 — a bad tool must not kill the loop
        log.error("%s raised: %s", call.name, exc)
    else:
        log.info("ok: %s", result)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", metavar="WAV", help="process one WAV file and exit")
    parser.add_argument(
        "--list-devices", action="store_true", help="print input devices and exit"
    )
    args = parser.parse_args()

    cfg = config.Config()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    if args.list_devices:
        import sounddevice as sd

        print(sd.query_devices())
        return 0

    tools.load()
    gemma = Gemma(cfg, tools.specs(), tools.describe())

    log.info("Gemma at %s, engine at %s", cfg.llama_url, cfg.engine_url)
    log.info(
        "wake word: %s%s",
        f"'{cfg.wake_word}'" if cfg.wake_word else "(none — every utterance acts)",
        " [DRY_RUN]" if cfg.dry_run else "",
    )

    if args.file:
        handle(cfg, gemma, audio.load_wav(args.file, cfg.sample_rate))
        return 0

    try:
        for wav in audio.Utterances(cfg):
            handle(cfg, gemma, wav)
    except KeyboardInterrupt:
        log.info("stopping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
