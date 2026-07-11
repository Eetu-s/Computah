# computah — Dockerized Moonshine microphone speech-to-text for Raspberry Pi

Listens to a USB microphone on a Raspberry Pi, transcribes speech with
[Moonshine](https://github.com/moonshine-ai/moonshine) (the `moonshine-voice`
package)

```
USB mic → Moonshine (in-process) → on each completed sentence → HTTP POST 
```

Each completed sentence is POSTed as JSON:

```json
{"text": "hello there", "start_time": 1.2, "duration": 0.9, "model": "tiny"}
```

## Requirements

- A **64-bit** Raspberry Pi OS (aarch64) with Docker.
- A **USB microphone** 

## Quick start (on the Pi)

```bash
# 1. Point POST_URL at your consumer service in docker-compose.yml
#   (only has a place holder for now)

# 2. Build and start the listener.
make up                 # or: docker compose up -d --build

# 3. Watch recognized sentences.
docker compose logs -f
```

Speak into the mic; each completed sentence is printed and POSTed to `POST_URL`.

## Choosing the speech-input path (STT vs agent)

There are two ways to turn speech into commands, selected by the
`COMPOSE_PROFILES` environment variable (defaulted in `.env`). Only the chosen
path's containers are built and started — the other is not included at all.

| `COMPOSE_PROFILES` | Speech containers | What it is |
| --- | --- | --- |
| `stt` (default) | `mic` | Cheap, offline Moonshine STT with exact phrase→command matching. |
| `agent` | `agent` + `llama` | Multimodal LLM (Gemma 4 via llama.cpp) that interprets speech and picks tools. |

Both paths POST to the shared **`computah-engine`**, which runs local commands
(e.g. `turn-on-led`) and forwards device commands to **`computah-cast`** (the
TV). So routing is unified — one command surface for STT and the LLM alike.
`computah-engine` and `computah-cast` run under **both** profiles.

```
              ┌── mic (stt) ──┐
speech ───────┤               ├──▶ computah-engine ──▶ (local cmd, e.g. LED)
              └─ agent (llm) ─┘         │
                                        └──▶ computah-cast ──▶ TV (DLNA/WOL/MQTT)
```

```bash
make up              # uses the default from .env (stt)
make up-agent        # run the LLM path instead
make up-stt          # force the STT path

# or directly:
COMPOSE_PROFILES=agent docker compose up -d --build
```

Change the default by editing `COMPOSE_PROFILES` in `.env`. There is one common
compose at the repo root that defines every service (the per-folder composes
were removed) — a single source of truth.

## Building on an x86 machine for the Pi

If you build on a laptop/desktop instead of the Pi, cross-build for arm64:

```bash
docker buildx build --platform linux/arm64 \
    --build-arg MOONSHINE_MODEL=tiny \
    -t computah-moonshine --load .
```

## Configuration

| Variable / arg | Default | Notes |
| --- | --- | --- |
| `POST_URL` | `http://consumer:9000/ingest` | Where sentences are POSTed. Unset → print only. |
| `MOONSHINE_MODEL` | `tiny` | `tiny` (bundled/offline) or `base` (downloaded, more accurate). |
| `MOONSHINE_LANGUAGE` | `en` | Non-English models are downloaded on first use. |
| `MOONSHINE_MIC_DEVICE` | (auto) | Input device index; list with `python -m sounddevice`. |
| `OMP_NUM_THREADS` | `4` | Inference threads; match the Pi's cores. |
| `mem_limit` (compose) | `2g` | Safety cap for a 4 GB Pi. |

> `base` and non-English models are fetched (and cached) on first use, so the
> container needs network access once. The default `tiny-en` needs none.


## Local development (native Linux with a mic)

```bash
cd STT
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # needs system libportaudio2
POST_URL=http://localhost:9000/ingest python listen.py
```

## Project layout

```
STT/                  # speech-to-text service (mic → transcribe → POST)
  core.py             # model resolution (which Moonshine model to load)
  listen.py           # mic listener: transcribe + POST each completed sentence
  Dockerfile
  requirements.txt
engine/               # command executor (receives commands, runs them)
  app.py
  commands/           # one module per command (e.g. turn_on_led.py)
  Dockerfile
docker-compose.yml    # runs both services
Makefile
```

