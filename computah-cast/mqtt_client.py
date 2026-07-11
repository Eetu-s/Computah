"""Client for the MQTT broker built into Hisense VIDAA TVs (TCP 36669).

Newer firmware wraps the broker in TLS with a self-signed certificate and
requires a one-time pairing where the TV shows a 4-digit code that must be
published back. Certificate validation is therefore disabled and the cipher
security level is lowered to tolerate the TV's weak/legacy certificate.
"""
import json
import logging
import ssl
import threading
import time

import paho.mqtt.client as mqtt

log = logging.getLogger("computah.mqtt")


class HisenseMQTT:
    def __init__(
        self,
        host,
        port=36669,
        username="hisenseservice",
        password="multimqttservice",
        client_name="computah",
        use_tls=True,
    ):
        self.host = host
        self.port = port
        self.client_name = client_name
        self.state = {}
        self._connected = threading.Event()

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"{client_name}-{int(time.time())}",
        )
        self.client.username_pw_set(username, password)

        if use_tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            try:
                # Hisense certs use small keys / legacy ciphers.
                ctx.set_ciphers("DEFAULT:@SECLEVEL=0")
            except ssl.SSLError:
                pass
            self.client.tls_set_context(ctx)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    # -- connection ---------------------------------------------------------
    def connect(self, timeout=10):
        self.client.connect(self.host, self.port, keepalive=60)
        self.client.loop_start()
        if not self._connected.wait(timeout):
            raise TimeoutError(f"MQTT connect to {self.host}:{self.port} timed out")

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()

    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        if reason_code != 0:
            log.warning("MQTT connect returned %s", reason_code)
            return
        log.info("Connected to Hisense MQTT broker at %s", self.host)
        # Watch every reply/broadcast so we can capture state and pairing codes.
        client.subscribe("/remoteapp/mobile/#")
        self._connected.set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        self._connected.clear()
        log.info("Disconnected from Hisense MQTT broker (%s)", reason_code)

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode(errors="ignore")
        log.debug("MQTT <- %s %s", msg.topic, payload)
        try:
            self.state[msg.topic] = json.loads(payload)
        except (ValueError, TypeError):
            self.state[msg.topic] = payload

    # -- commands -----------------------------------------------------------
    def _topic(self, service, action):
        return f"/remoteapp/tv/{service}/{self.client_name}/actions/{action}"

    def _publish(self, service, action, payload=""):
        topic = self._topic(service, action)
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload)
        log.info("MQTT -> %s %s", topic, payload)
        self.client.publish(topic, payload)

    def send_key(self, key):
        self._publish("remote_service", "sendkey", key)

    def launch_app(self, app):
        self._publish("ui_service", "launchapp", app)

    def change_source(self, source):
        self._publish("ui_service", "changesource", source)

    def set_volume(self, level):
        self._publish("platform_service", "changevolume", str(int(level)))

    def get_state(self):
        self._publish("ui_service", "gettvstate", "")

    def authenticate(self, code):
        """Complete pairing with the 4-digit code shown on the TV."""
        self._publish(
            "ui_service", "authenticationcode", {"authNum": int(code)}
        )

    def power(self):
        """Toggle standby (KEY_POWER). Use WOL to turn on from full-off."""
        self.send_key("KEY_POWER")
