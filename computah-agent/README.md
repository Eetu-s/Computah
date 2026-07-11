# computah-agent

Speech in, tool call out. Listens to the mic, hands each utterance to **Gemma 4
as audio**, and runs whichever tool Gemma picks.

```
USB mic → VAD (cut an utterance) → Gemma 4 (llama.cpp) → tool call → computah-cast
```

There is **no transcription step**. Gemma 4 ingests audio natively, so one
request goes from raw speech to a decision. This runs *alongside* the Moonshine
listener in `../app`, not through it — Moonshine turns speech into text for a
consumer service; this turns speech into actions.

## Why llama.cpp and not Ollama

Gemma 4's audio support and its tool-call parser are both broken in Ollama at
the time of writing (it crashes on audio requests, and its parser mishandles
Gemma 4's hybrid attention architecture). llama.cpp is the working runtime for
audio + tools together. Tool calling requires `--jinja`; audio requires an
`--mmproj` projector file.

## Models

Audio input is only on the multimodal variants. E2B is the one that fits a Pi.

| Variant | Audio | ~RAM @ Q4 | Notes |
| --- | --- | --- | --- |
| **E2B** | yes | ~2 GB | The default here. Workable on a Pi 5 (8 GB). |
| **E4B** | yes | ~3.5 GB | Better decisions; noticeably slower on a Pi. |
| **12B** | yes | ~9 GB | Needs a real machine — point `LLAMA_URL` at a LAN box. |
| 26B / 31B | **no** | – | Text-only. Not usable here. |

Audio is capped at **30 s** by the model. `MAX_UTTERANCE_SEC` (default 15 s)
keeps clips under that; longer speech is truncated, not dropped.

## Quick start (on the Pi)

```bash
# 1. Fetch the weights *and* the audio projector. Both are required — without
#    the projector llama-server reports "audio input is not supported".
mkdir -p models && REPO=https://huggingface.co/ggml-org/gemma-4-E2B-it-GGUF/resolve/main
curl -L -o models/gemma-4-E2B-it-Q8_0.gguf        $REPO/gemma-4-E2B-it-Q8_0.gguf
curl -L -o models/mmproj-gemma-4-E2B-it-Q8_0.gguf $REPO/mmproj-gemma-4-E2B-it-Q8_0.gguf

# 2. Point CAST_URL at computah-cast (defaults to the same host, :8000).
# 3. Bring up llama-server + the agent.
docker compose up -d --build
docker compose logs -f
```

> E2B ships **only** as `Q8_0` / `bf16` — there is no `Q4_K_M`. Don't use
> llama.cpp's `-hf` auto-download; it hangs on some builds. Fetch by hand.

Then say: *"Computah, put the picture on the TV."*

> The first run downloads the model (~2 GB). `llama` and `agent` both use host
> networking, so the agent reaches llama-server and computah-cast on
> `127.0.0.1`.

## Running it locally

```bash
brew install llama.cpp
pip install -r requirements.txt

# 1. Weights + audio projector (~5.5 GB). Note E4B here, not E2B.
mkdir -p models && REPO=https://huggingface.co/ggml-org/gemma-4-E4B-it-GGUF/resolve/main
curl -L -o models/gemma-4-E4B-it-Q4_K_M.gguf       $REPO/gemma-4-E4B-it-Q4_K_M.gguf
curl -L -o models/mmproj-gemma-4-E4B-it-Q8_0.gguf  $REPO/mmproj-gemma-4-E4B-it-Q8_0.gguf

# 2. Gemma, on the GPU.
llama-server -m models/gemma-4-E4B-it-Q4_K_M.gguf \
             --mmproj models/mmproj-gemma-4-E4B-it-Q8_0.gguf \
             --jinja -ngl 99 -c 8192 --host 127.0.0.1 --port 8080

# 3. computah-cast (in ../computah-cast). IMAGE_PATH must be a real local path
#    the default /data/current.jpg is not writable by a regular user.
TV_IP=<tv-ip> TV_MAC=<tv-mac> IMAGE_PATH="$PWD/data/current.png" \
  python app.py

# 4. The agent, on the built-in mic.
LLAMA_URL=http://127.0.0.1:8080 CAST_URL=http://127.0.0.1:8000 python agent.py
```

Casting locally works exactly as from the Pi: it serves the image over HTTP
on the LAN and hands the TV that URL over DLNA. MQTT (used only for power and
key presses) will fail while the TV is in standby but that's expected and it does
not affect casting.

## Testing without a mic (or without a Pi)

`--file` runs one recording through the whole path — useful on a laptop:

```bash
pip install -r requirements.txt
python agent.py --list-devices                    # find MIC_DEVICE
python agent.py --file test.wav                   # one utterance, then exit
DRY_RUN=true python agent.py                      # log the tool, don't run it
```

Any WAV works — it is downmixed and resampled to the 16 kHz mono Gemma needs.
`DRY_RUN=true` is the fastest way to tune the mic: it prints the tool Gemma
chose without touching the TV.

You can also synthesise test speech instead of recording it. Pad the end, 
`say` clips the final word, which will silently cost you the most important one:

```bash
say -v Daniel -o /tmp/c.aiff "Computah, turn the volume up."
afconvert -f WAVE -d LEI16@16000 -c 1 /tmp/c.aiff /tmp/c.wav
python agent.py --file /tmp/c.wav
```

If a command is being misread, ask Gemma what it actually heard before blaming
the prompt — POST the same WAV with "transcribe this exactly" instead of tools.
That is how the two bugs above were found.

## Adding a tool

Drop a function in `tools/`. It is discovered at import — there is no registry
to update and nothing else to edit.

```python
# tools/lights.py
import requests
from . import tool

@tool(
    "set_lights",
    "Turn the living room lights on or off.",   # the model reads this
    {"on": {"type": "boolean", "description": "True for on, False for off."}},
    required=["on"],
)
def set_lights(cfg, on: bool):
    requests.post(f"{cfg.lights_url}/state", json={"on": on}, timeout=5)
    return f"lights {'on' if on else 'off'}"
```

The description *is* the prompt — it's what Gemma matches speech against, so
write it the way someone would say it. The registry drops arguments the model
invents and rejects tool names it hallucinates, so a bad guess is logged and
skipped rather than crashing the listener.

`no_action` (in `tools/core.py`) is what Gemma picks when the speech wasn't
addressed to it. Keep it.

## How it decides to act

The mic hears everything — conversation, the TV itself. Two things stop that
from firing tools:

1. **The VAD** only cuts an utterance when energy rises above the rolling noise
   floor, so silence costs nothing.
2. **The wake word** (`WAKE_WORD`, default `computah`) is enforced in the system
   prompt: Gemma is told to call `no_action` unless it hears it. Set
   `WAKE_WORD=""` to act on every utterance.

A false VAD trigger therefore costs one Gemma call, not a wrong action.

The wake word is matched **by ear, not by spelling** — Gemma transcribes
"computah" as *"computer"*, so the prompt tells it to accept anything that
sounds like the name. Demanding the literal string made it refuse valid
commands. Keep that in mind if you change `WAKE_WORD` to something whose
spelling is far from its pronunciation.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `LLAMA_URL` | `http://llama:8080` | llama-server endpoint. Point at a LAN box to use a bigger model. |
| `LLAMA_MODEL` | `gemma-4` | Sent in the request; llama-server ignores it. |
| `LLAMA_TIMEOUT` | `120` | Seconds. Raise it — a Pi is slow. |
| `CAST_URL` | `http://localhost:8000` | computah-cast REST API. |
| `WAKE_WORD` | `computah` | `""` disables the gate; every utterance acts. |
| `DRY_RUN` | `false` | Log the chosen tool without running it. |
| `MIC_DEVICE` | (auto) | Input index; see `--list-devices`. |
| `VAD_THRESHOLD` | `3.0` | How far over the noise floor counts as speech. |
| `VAD_MIN_RMS` | `0.012` | Absolute gate, so hiss can't trigger the ratio. |
| `SILENCE_SEC` | `0.8` | Silence that ends an utterance. |
| `PREROLL_SEC` | `0.4` | Audio kept from before the trigger (saves the first word). |
| `MIN_UTTERANCE_SEC` | `0.4` | Minimum *speech* (excl. pre-roll); rejects coughs. |
| `MAX_UTTERANCE_SEC` | `15` | Hard-capped at 30 by the model. |
| `LOG_LEVEL` | `INFO` | `DEBUG` shows VAD decisions. |

## Troubleshooting

- **Nothing triggers** – Run with `LOG_LEVEL=DEBUG` to see VAD decisions. Lower
  `VAD_THRESHOLD`, or set `MIC_DEVICE` (the default input may be the wrong one).
- **It triggers constantly** – Expected in a loud room; check it still answers
  `no_action`. Raise `VAD_THRESHOLD` / `VAD_MIN_RMS` to cut the wasted calls.
- **"recovered a tool call from message content"** – llama-server is not
  applying the tool template. Confirm `--jinja` is in its command.
- **"audio input is not supported"** – The `--mmproj` projector is missing or is
  the wrong one for the model. Check the filename matches your variant.
- **Every command becomes `no_action`** – Gemma isn't hearing the wake word. Try
  `WAKE_WORD=""` to confirm the audio path works, then reintroduce it.
