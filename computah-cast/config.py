"""Environment-driven configuration for computah-cast.

Every setting can be overridden with an environment variable so the whole
service is configured through the Docker `environment:` block or `-e` flags.
"""
import os


def _bool(value, default=False):
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


class Config:
    def __init__(self, env=None):
        env = env or os.environ

        # --- HTTP image host -------------------------------------------------
        self.http_host = env.get("HTTP_HOST", "0.0.0.0")
        self.http_port = int(env.get("HTTP_PORT", "8000"))
        # IP the TV should use to reach this Pi. Auto-detected when unset.
        self.advertise_ip = env.get("ADVERTISE_IP") or None
        # Where the currently-served image lives (persisted on a volume).
        self.image_path = env.get("IMAGE_PATH", "/data/current.jpg")
        # Optional seed image copied to image_path on first start.
        self.default_image = env.get("DEFAULT_IMAGE") or None

        # --- Target TV -------------------------------------------------------
        self.tv_ip = env.get("TV_IP") or None
        self.tv_mac = env.get("TV_MAC") or None  # for Wake-on-LAN

        # --- Display method: "dlna" (default) or "browser" -------------------
        self.display_method = env.get("DISPLAY_METHOD", "dlna").lower()

        # --- DLNA ------------------------------------------------------------
        # Skip SSDP discovery by hard-coding the AVTransport control URL.
        self.dlna_control_url = env.get("DLNA_CONTROL_URL") or None
        self.dlna_discovery_timeout = int(env.get("DLNA_DISCOVERY_TIMEOUT", "3"))

        # --- MQTT (Hisense remote broker on TCP 36669) -----------------------
        self.mqtt_enabled = _bool(env.get("MQTT_ENABLED"), True)
        self.mqtt_port = int(env.get("MQTT_PORT", "36669"))
        self.mqtt_user = env.get("MQTT_USER", "hisenseservice")
        self.mqtt_pass = env.get("MQTT_PASS", "multimqttservice")
        self.mqtt_client_name = env.get("MQTT_CLIENT_NAME", "computah")
        self.mqtt_tls = _bool(env.get("MQTT_TLS"), True)

        # --- Behaviour -------------------------------------------------------
        self.auto_cast = _bool(env.get("AUTO_CAST"), True)
        self.wake_on_cast = _bool(env.get("WAKE_ON_CAST"), True)
        self.log_level = env.get("LOG_LEVEL", "INFO").upper()
