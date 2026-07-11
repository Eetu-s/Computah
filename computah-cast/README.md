# computah-cast

Host an image on a **Raspberry Pi 5** and display it on a **Hisense VIDAA TV**.

The Pi serves the current image over HTTP, then instructs the TV to fetch and
show it. A tiny REST API lets you swap the image and drive the TV at runtime.

## How the image gets on screen

Hisense's documented MQTT interface (see the repo root `README.md`) can change
channels, launch apps and press remote keys, but has **no "show this image
URL" command**. Two approaches are supported here:

| `DISPLAY_METHOD` | How it works | Needs |
| --- | --- | --- |
| `dlna` *(default)* | Push the image URL to the TV's UPnP MediaRenderer via `SetAVTransportURI` + `Play`. Works on most VIDAA sets with no TV-side app. | TV powered on; DLNA/"Anyview" enabled |
| `browser` | Launch the TV browser at the Pi's full-screen page via MQTT `launchapp`. | A browser app on the TV; payload may need tuning per model |

MQTT is still used for **power/pairing/keys** even in `dlna` mode.

## Architecture

```
        upload / cast / power (REST)
  you ─────────────────────────────▶  Raspberry Pi (this container)
                                          │  hosts  http://PI:8000/image
                                          │
             ┌────────────────────────────┴───────────────────────────┐
             │ DLNA: SetAVTransportURI+Play        MQTT :36669 (TLS)   │
             ▼                                     WOL (power on)       ▼
        Hisense VIDAA TV  ◀── fetches image over HTTP ──────────────────
```

## Files

- `app.py` – Flask server: hosts the image + REST control API + orchestration
- `dlna.py` – SSDP discovery and AVTransport SOAP calls
- `mqtt_client.py` – Hisense MQTT client (TLS, self-signed cert, pairing, keys)
- `wol.py` / `util.py` / `config.py` – Wake-on-LAN, IP detection, env config

## Quick start (Docker Compose on the Pi)

1. Edit `docker-compose.yml` and set at least `TV_IP` and `TV_MAC`.
2. (Optional) drop a starting image at `./data/current.jpg`.
3. Build and run:

   ```bash
   docker compose up -d --build
   ```

> **Host networking is required** (`network_mode: host`) so the container can
> do SSDP multicast discovery, broadcast Wake-on-LAN packets, and be reachable
> by the TV. It is already set in the compose file.

### Or with plain Docker

```bash
docker build -t computah-cast .
docker run -d --name computah-cast --network host --restart unless-stopped \
  -e TV_IP=192.168.1.50 \
  -e TV_MAC=AA:BB:CC:DD:EE:FF \
  -e DISPLAY_METHOD=dlna \
  -v "$PWD/data:/data" \
  computah-cast
```

### Run without Docker (for testing)

```bash
pip install -r requirements.txt
TV_IP=192.168.1.50 TV_MAC=AA:BB:CC:DD:EE:FF python app.py
```

## First-time MQTT pairing

Newer TVs show a 4-digit code the first time an app connects. Read it off the
screen and send it back:

```bash
curl -X POST "http://<PI_IP>:8000/pair" \
     -H 'Content-Type: application/json' -d '{"authNum": 1234}'
```

After pairing succeeds the MQTT commands (power, keys, source) work.

## REST API

| Method & path | Body / query | Description |
| --- | --- | --- |
| `POST /upload` | image file (`file` field) or raw bytes; `?cast=false` to skip | Replace the hosted image and (by default) re-cast it |
| `POST /cast` | – | Wake the TV (if `TV_MAC` set) and display the current image |
| `POST /power` | – | WOL + MQTT `KEY_POWER` (toggle standby) |
| `POST /pair` | `{"authNum": 1234}` | Complete MQTT pairing |
| `POST /key` | `{"key": "KEY_HOME"}` | Send a remote key |
| `POST /app` | a `launchapp` JSON body | Launch an app |
| `POST /source` | `{"sourceid": "4"}` | Change input source |
| `GET /state` | – | Ask for and return the last known TV state |
| `GET /health` | – | Status, detected IP, MQTT connectivity |
| `GET /image` | – | The currently hosted image (what the TV fetches) |
| `GET /` | – | Full-screen black-background image page (used by `browser` mode) |

### Examples

```bash
# Upload a new image and cast it immediately
curl -X POST -F "file=@poster.jpg" http://<PI_IP>:8000/upload

# Just re-display the current image
curl -X POST http://<PI_IP>:8000/cast

# Power on / press a key
curl -X POST http://<PI_IP>:8000/power
curl -X POST "http://<PI_IP>:8000/key" -d '{"key":"KEY_HOME"}' -H 'Content-Type: application/json'
```

## Configuration (environment variables)

| Variable | Default | Description |
| --- | --- | --- |
| `TV_IP` | – | TV IP address (required for MQTT/DLNA targeting) |
| `TV_MAC` | – | TV MAC for Wake-on-LAN power-on |
| `DISPLAY_METHOD` | `dlna` | `dlna` or `browser` |
| `HTTP_PORT` | `8000` | Port the image is hosted on |
| `ADVERTISE_IP` | auto | Pi IP the TV should use; set if auto-detection is wrong |
| `IMAGE_PATH` | `/data/current.jpg` | Where the current image is stored |
| `DEFAULT_IMAGE` | – | Seed image copied to `IMAGE_PATH` on first start |
| `AUTO_CAST` | `true` | Cast the image on startup |
| `WAKE_ON_CAST` | `true` | Send WOL before each cast |
| `DLNA_CONTROL_URL` | auto | Skip SSDP by hard-coding the AVTransport control URL |
| `DLNA_DISCOVERY_TIMEOUT` | `3` | Seconds to wait for SSDP replies |
| `MQTT_ENABLED` | `true` | Enable the Hisense MQTT client |
| `MQTT_PORT` | `36669` | Hisense broker port |
| `MQTT_USER` / `MQTT_PASS` | `hisenseservice` / `multimqttservice` | Broker credentials |
| `MQTT_CLIENT_NAME` | `computah` | App name segment used in MQTT topics |
| `MQTT_TLS` | `true` | Use TLS (needed on newer firmware) |
| `LOG_LEVEL` | `INFO` | `DEBUG` to see all MQTT traffic |

## Troubleshooting

- **"No DLNA AVTransport renderer found"** – The TV must be **on** and have
  DLNA/Anyview enabled. Try `POST /power`, wait, then `POST /cast`. You can also
  bypass discovery by setting `DLNA_CONTROL_URL`.
- **MQTT connect fails / TLS errors** – Older sets use legacy certs; TLS
  verification is already disabled and the cipher security level lowered. If it
  still fails, try `MQTT_TLS=false` (very old firmware ran plain MQTT).
- **Wrong image URL / TV can't fetch** – Auto-detection picked the wrong NIC;
  set `ADVERTISE_IP` to the Pi's LAN address.
- **`browser` mode does nothing** – The `launchapp` payload (`name`/`url`) is
  model specific; enumerate apps via MQTT `applist` and adjust `_cast_browser`.
