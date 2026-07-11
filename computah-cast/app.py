"""computah-cast: host an image on a Raspberry Pi and display it on a Hisense
VIDAA TV.

The Pi serves the current image over HTTP; the TV is then told to fetch and
display it. Two display methods are supported:

  * ``dlna``    - push the image URL to the TV's UPnP MediaRenderer (default,
                  works without any TV-side app).
  * ``browser`` - launch the TV browser at the Pi's full-screen page via MQTT
                  (model dependent; adjust MQTT_* / the launch payload).

A small REST API allows swapping the image and driving the TV at runtime.
"""
import logging
import mimetypes
import os
import shutil
import threading
import time

from flask import Flask, Response, abort, jsonify, request, send_file

import config
import dlna
import util
import wol
from mqtt_client import HisenseMQTT

cfg = config.Config()
logging.basicConfig(
    level=cfg.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("computah")

app = Flask(__name__)
tv = None  # HisenseMQTT instance, set up in startup()

INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>computah-cast</title>
<style>
  html,body{margin:0;height:100%;background:#000;overflow:hidden}
  img{width:100vw;height:100vh;object-fit:contain}
</style></head>
<body><img id="img" src="/image?t=__T__" alt="">
<script>
  setInterval(function(){
    document.getElementById('img').src='/image?t='+Date.now();
  }, 15000);
</script></body></html>"""


# --- helpers ---------------------------------------------------------------
def advertise_ip():
    return cfg.advertise_ip or util.get_local_ip(cfg.tv_ip or "8.8.8.8")


def image_mime():
    return mimetypes.guess_type(cfg.image_path)[0] or "image/jpeg"


def image_url():
    ext = os.path.splitext(cfg.image_path)[1].lstrip(".") or "jpg"
    return f"http://{advertise_ip()}:{cfg.http_port}/image.{ext}?t={int(time.time())}"


def do_cast():
    """Wake the TV if configured, then display the current image."""
    if not os.path.exists(cfg.image_path):
        raise FileNotFoundError(f"No image at {cfg.image_path}")

    if cfg.wake_on_cast and cfg.tv_mac:
        try:
            wol.wake(cfg.tv_mac)
            log.info("Sent WOL to %s", cfg.tv_mac)
        except Exception as exc:  # noqa: BLE001
            log.warning("WOL failed: %s", exc)

    url = image_url()

    if cfg.display_method == "browser":
        return _cast_browser(url)
    return _cast_dlna(url)


def _cast_dlna(url):
    last_error = None
    # The renderer may take a few seconds to come up after a wake.
    for attempt in range(1, 6):
        try:
            control_url = dlna.cast_image(
                url,
                control_url=cfg.dlna_control_url,
                target_ip=cfg.tv_ip,
                mime=image_mime(),
                discovery_timeout=cfg.dlna_discovery_timeout,
            )
            return {"method": "dlna", "url": url, "control_url": control_url}
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            log.warning("DLNA cast attempt %d/5 failed: %s", attempt, exc)
            time.sleep(2)
    raise RuntimeError(f"DLNA cast failed: {last_error}")


def _cast_browser(url):
    if tv is None:
        raise RuntimeError("browser display method requires MQTT (MQTT_ENABLED)")
    page = f"http://{advertise_ip()}:{cfg.http_port}/"
    tv.launch_app({"name": "Browser", "urlType": 37, "storeType": 0, "url": page})
    return {"method": "browser", "page": page, "image": url}


# --- image hosting ---------------------------------------------------------
@app.route("/")
def index():
    return Response(
        INDEX_HTML.replace("__T__", str(int(time.time()))), mimetype="text/html"
    )


@app.route("/image")
@app.route("/image.<ext>")
def serve_image(ext=None):
    if not os.path.exists(cfg.image_path):
        abort(404, "no image uploaded yet")
    return send_file(cfg.image_path, mimetype=image_mime(), conditional=False)


@app.route("/upload", methods=["POST"])
def upload():
    """Replace the hosted image (multipart 'file' field or raw body) and cast."""
    if "file" in request.files:
        data = request.files["file"].read()
    else:
        data = request.get_data()
    if not data:
        return jsonify(error="no image data supplied"), 400

    os.makedirs(os.path.dirname(cfg.image_path) or ".", exist_ok=True)
    with open(cfg.image_path, "wb") as fh:
        fh.write(data)

    result = {"saved": cfg.image_path, "bytes": len(data)}
    if request.args.get("cast", "true").lower() in ("1", "true", "yes"):
        try:
            result["cast"] = do_cast()
        except Exception as exc:  # noqa: BLE001
            result["cast_error"] = str(exc)
    return jsonify(result)


# --- TV control ------------------------------------------------------------
@app.route("/cast", methods=["POST"])
def cast():
    try:
        return jsonify(do_cast())
    except Exception as exc:  # noqa: BLE001
        return jsonify(error=str(exc)), 500


@app.route("/power", methods=["POST"])
def power():
    result = {}
    if cfg.tv_mac:
        try:
            wol.wake(cfg.tv_mac)
            result["wol"] = cfg.tv_mac
        except Exception as exc:  # noqa: BLE001
            result["wol_error"] = str(exc)
    if tv is not None:
        tv.power()
        result["mqtt"] = "KEY_POWER"
    return jsonify(result)


@app.route("/pair", methods=["POST"])
def pair():
    """Complete MQTT pairing with the 4-digit code shown on the TV."""
    if tv is None:
        return jsonify(error="MQTT not enabled"), 400
    code = (request.get_json(silent=True) or {}).get("authNum") or request.args.get(
        "authNum"
    )
    if not code:
        return jsonify(error="provide authNum (the 4-digit code on screen)"), 400
    tv.authenticate(code)
    return jsonify(paired="requested", authNum=code)


@app.route("/key", methods=["POST"])
def key():
    if tv is None:
        return jsonify(error="MQTT not enabled"), 400
    value = (request.get_json(silent=True) or {}).get("key") or request.args.get("key")
    if not value:
        return jsonify(error="provide key, e.g. KEY_HOME"), 400
    tv.send_key(value)
    return jsonify(sent=value)


@app.route("/app", methods=["POST"])
def launch_app():
    if tv is None:
        return jsonify(error="MQTT not enabled"), 400
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(error="provide a launchapp JSON body"), 400
    tv.launch_app(payload)
    return jsonify(launched=payload)


@app.route("/source", methods=["POST"])
def source():
    if tv is None:
        return jsonify(error="MQTT not enabled"), 400
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(error='provide {"sourceid": "..."}'), 400
    tv.change_source(payload)
    return jsonify(source=payload)


@app.route("/state")
def state():
    if tv is None:
        return jsonify(error="MQTT not enabled"), 400
    tv.get_state()
    return jsonify(tv.state)


@app.route("/health")
def health():
    return jsonify(
        status="ok",
        advertise_ip=advertise_ip(),
        image_present=os.path.exists(cfg.image_path),
        display_method=cfg.display_method,
        mqtt_connected=tv is not None and tv._connected.is_set(),
        tv_ip=cfg.tv_ip,
    )


# --- startup ---------------------------------------------------------------
def startup():
    global tv

    if cfg.default_image and not os.path.exists(cfg.image_path):
        os.makedirs(os.path.dirname(cfg.image_path) or ".", exist_ok=True)
        try:
            shutil.copy(cfg.default_image, cfg.image_path)
            log.info("Seeded image from %s", cfg.default_image)
        except OSError as exc:
            log.warning("Could not seed default image: %s", exc)

    if cfg.mqtt_enabled and cfg.tv_ip:
        tv = HisenseMQTT(
            cfg.tv_ip,
            port=cfg.mqtt_port,
            username=cfg.mqtt_user,
            password=cfg.mqtt_pass,
            client_name=cfg.mqtt_client_name,
            use_tls=cfg.mqtt_tls,
        )
        try:
            tv.connect()
        except Exception as exc:  # noqa: BLE001
            log.warning("MQTT connect failed (continuing): %s", exc)

    if cfg.auto_cast and os.path.exists(cfg.image_path):
        def _initial_cast():
            time.sleep(3)  # let the TV / network settle
            try:
                do_cast()
            except Exception as exc:  # noqa: BLE001
                log.warning("Initial auto-cast failed: %s", exc)

        threading.Thread(target=_initial_cast, daemon=True).start()


def main():
    startup()
    log.info(
        "computah-cast serving on %s:%s (advertising %s)",
        cfg.http_host,
        cfg.http_port,
        advertise_ip(),
    )
    try:
        from waitress import serve

        serve(app, host=cfg.http_host, port=cfg.http_port)
    except ImportError:
        app.run(host=cfg.http_host, port=cfg.http_port, threaded=True)


if __name__ == "__main__":
    main()
