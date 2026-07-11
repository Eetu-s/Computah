"""Command: turn on an LED.

Reached at ``POST /commands/turn-on-led``. No hardware logic yet — this is a
stub that just logs. Replace the body of ``turn_on_led`` with real GPIO code
(e.g. via ``gpiozero``) when wiring up an actual LED.
"""

from __future__ import annotations

from . import command


@command("turn-on-led")
def turn_on_led(params: dict) -> dict:
    # TODO: drive a real LED here (e.g. gpiozero.LED(pin).on()).
    print("Executing command: turn on LED", flush=True)
    return {
        "command": "turn-on-led",
        "status": "ok",
        "detail": "LED turned on (stub — no hardware yet)",
    }
