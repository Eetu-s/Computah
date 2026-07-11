# computah — Dockerized Moonshine speech-to-text for Raspberry Pi

A small, self-contained speech-to-text service built on
[Moonshine](https://github.com/moonshine-ai/moonshine) (the `moonshine-voice`
package). 


## Requirements

- A **64-bit** Raspberry Pi OS (aarch64) with Docker.
- Audio in a common format (wav/flac/ogg/…); it's downmixed to mono and the
  native library resamples it to what the model needs.

## Quick start (on the Pi)

```bash
# Build the image (bundles the tiny-en model, no downloads).
make build            # or: docker build -t computah-moonshine .

# Start the HTTP service on port 8000.
make up               # or: docker compose up -d --build

# Check it's alive.
curl http://localhost:8000/health
# {"status":"ok","model":"tiny"}

# Transcribe the included sample.
curl -F "file=@samples/yoursample.wav" http://localhost:8000/transcribe
# {"text":"What ever your sample has transcribed here as text","model":"tiny","seconds":_}
```

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
| `MOONSHINE_MODEL` | `tiny` | `tiny` (bundled/offline) or `base` (downloaded, more accurate). |
| `MOONSHINE_LANGUAGE` | `en` | Non-English models are downloaded on first use. |
| `OMP_NUM_THREADS` | `4` | Inference threads; match the Pi's cores. |
| `mem_limit` (compose) | `2g` | Safety cap for a 4 GB Pi. |

> `base` and non-English models are fetched (and cached) on first use, so the
> container needs network access once. The default `tiny-en` needs none.

## HTTP API

| Method | Path | Body | Response |
| --- | --- | --- | --- |
| `GET` | `/health` | — | `{"status","model"}` |
| `POST` | `/transcribe` | multipart file field `file` | `{"text","model","seconds"}` |


## Project layout

```
app/
  core.py         # model loading + audio decode + inference (shared)
  transcribe.py   # CLI entry point
  server.py       # FastAPI HTTP service
Dockerfile
docker-compose.yml
Makefile
samples/          # audio test clip

