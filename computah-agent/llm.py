"""Gemma 4 client (llama.cpp server, OpenAI-compatible API).

Gemma 4 ingests audio natively, so one request goes from raw speech to a tool
call — there is no transcription step and no text model in between.

Two things the runtime cares about:
  * audio rides in the message content as an `input_audio` part (base64 WAV);
  * tool calling needs llama-server started with `--jinja`, otherwise the
    template never emits a tool call and everything lands in `content`.

Ollama is not an option here: it crashes on Gemma 4 audio and its tool-call
parser is broken for this architecture.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from dataclasses import dataclass

import requests

log = logging.getLogger("computah.llm")

_SYSTEM = """\
You control a Raspberry Pi in a living room. You are given a recording of \
whatever the microphone just picked up, and you must respond with exactly one \
tool call.

The recording is unfiltered room audio. It is often *not* addressed to you: it \
may be a conversation between people, the television, or background noise.

Available tools:
{tools}

Rules:
- Reply with exactly one tool call. Never answer in prose. Never call two tools.
- Listen to what the speaker actually asked for and pick the matching argument. \
Opposites matter: "up" is not "down", "on" is not "off".
{gate}"""

# The gate goes last on purpose: it is the rule the model is most likely to
# drop, and trailing instructions carry the most weight.
_GATE_WAKE = """\
- The speaker is addressing you ONLY if you hear them call you "{wake}" at the \
start of the recording. Accept anything that plainly sounds like "{wake}", \
however you would spell it — you are hearing a spoken name, not reading it.
- If nobody calls you "{wake}", you MUST call no_action — even if the recording \
contains a clear, well-formed instruction. A command with no "{wake}" in it is \
one person talking to another person, or the television talking to nobody. It \
is not for you. Do not act on it."""

_GATE_OPEN = """\
- Treat the speech as an instruction whenever it plausibly is one."""


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict


def system_prompt(cfg, tool_descriptions: str) -> str:
    gate = (
        _GATE_WAKE.format(wake=cfg.wake_word)
        if cfg.wake_word
        else _GATE_OPEN
    )
    return _SYSTEM.format(gate=gate, tools=tool_descriptions)


class Gemma:
    def __init__(self, cfg, tool_specs: list[dict], tool_descriptions: str):
        self.cfg = cfg
        self.tool_specs = tool_specs
        self.system = system_prompt(cfg, tool_descriptions)
        self.session = requests.Session()

    def decide(self, wav: bytes) -> ToolCall | None:
        """Send one utterance to Gemma and return the tool call it chose."""
        payload = {
            "model": self.cfg.llama_model,
            "temperature": self.cfg.temperature,
            "messages": [
                {"role": "system", "content": self.system},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": base64.b64encode(wav).decode("ascii"),
                                "format": "wav",
                            },
                        },
                    ],
                },
            ],
            "tools": self.tool_specs,
            "tool_choice": "auto",
        }

        resp = self.session.post(
            f"{self.cfg.llama_url}/v1/chat/completions",
            json=payload,
            timeout=self.cfg.llama_timeout,
        )
        resp.raise_for_status()
        message = resp.json()["choices"][0]["message"]

        calls = message.get("tool_calls") or []
        if calls:
            fn = calls[0]["function"]
            return ToolCall(fn["name"], _parse_args(fn.get("arguments")))

        # Templates for this model family have historically emitted the call as
        # plain text instead of populating tool_calls. Recover it if so.
        return _salvage(message.get("content") or "")


def _parse_args(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        log.warning("could not parse tool arguments: %r", raw)
        return {}
    return args if isinstance(args, dict) else {}


def _salvage(content: str) -> ToolCall | None:
    """Pull a {"name": ..., "arguments": {...}} object out of a prose response."""
    if not content.strip():
        return None

    for match in re.finditer(r"\{.*\}", content, re.DOTALL):
        try:
            obj = json.loads(match.group())
        except json.JSONDecodeError:
            continue
        name = obj.get("name") or obj.get("tool") or obj.get("function")
        if isinstance(name, str):
            log.warning("recovered a tool call from message content (check --jinja)")
            return ToolCall(name, _parse_args(obj.get("arguments") or obj.get("parameters")))

    log.warning("no tool call in response: %s", content.strip()[:200])
    return None
