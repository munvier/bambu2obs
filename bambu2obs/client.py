"""Local MQTT client (LAN mode) for Bambu Lab printers."""

import json
import logging
import ssl
import threading
import uuid
from typing import Any, Callable

import paho.mqtt.client as mqtt

log = logging.getLogger(__name__)

MQTT_PORT = 8883
MQTT_USER = "bblp"


def _deep_merge(dst: dict, src: dict) -> None:
    """Merge src into dst: the printer often sends only the fields that changed."""
    for key, value in src.items():
        if isinstance(value, dict) and isinstance(dst.get(key), dict):
            _deep_merge(dst[key], value)
        else:
            dst[key] = value


class BambuClient:
    def __init__(
        self,
        host: str,
        serial: str,
        access_code: str,
        on_update: Callable[[dict[str, Any], bool], None] | None = None,
    ) -> None:
        self.host = host
        self.serial = serial
        self.on_update = on_update
        self.state: dict[str, Any] = {}
        self.connected = False
        self._lock = threading.Lock()
        self._sequence_id = 0

        self.report_topic = f"device/{serial}/report"
        self.request_topic = f"device/{serial}/request"

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f"bambu2obs-{uuid.uuid4().hex[:8]}")
        self._client.username_pw_set(MQTT_USER, access_code)
        # The printer uses a self-signed certificate.
        self._client.tls_set(cert_reqs=ssl.CERT_NONE)
        self._client.tls_insecure_set(True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message
        self._client.on_subscribe = self._on_subscribe

    # --- lifecycle -----------------------------------------------------------

    def start(self) -> None:
        """Connect in the background, with automatic reconnection."""
        log.info("Connecting to %s:%d ...", self.host, MQTT_PORT)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.connect_async(self.host, MQTT_PORT, keepalive=60)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.disconnect()
        self._client.loop_stop()

    # --- commands ------------------------------------------------------------

    def publish(self, payload: dict[str, Any]) -> None:
        info = self._client.publish(self.request_topic, json.dumps(payload))
        log.debug("TX %s -> %s (rc=%s)", self.request_topic, payload, info.rc)

    def _next_seq(self) -> str:
        self._sequence_id += 1
        return str(self._sequence_id)

    def request_full_state(self) -> None:
        """Ask the printer to send its full state."""
        self.publish({"pushing": {"sequence_id": self._next_seq(), "command": "pushall"}})

    def get_version(self) -> None:
        self.publish({"info": {"sequence_id": self._next_seq(), "command": "get_version"}})

    # --- paho callbacks ------------------------------------------------------

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error("Connection refused: %s (access code / LAN mode?)", reason_code)
            return
        log.info("Connected, subscribing to %s", self.report_topic)
        self.connected = True
        self._notify()
        client.subscribe(self.report_topic)
        self.request_full_state()

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties) -> None:
        for rc in reason_codes:
            if rc.is_failure:
                log.error("Subscription refused: %s (serial number / developer mode?)", rc)
            else:
                log.info("Subscription accepted (%s)", rc)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        log.warning("Disconnected: %s", reason_code)
        self.connected = False
        self._notify()

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        log.debug("RX raw %s (%d bytes)", msg.topic, len(msg.payload))
        try:
            data = json.loads(msg.payload)
        except json.JSONDecodeError:
            log.warning("Ignoring non-JSON message on %s", msg.topic)
            return

        log.debug("RX %s", data)
        if "print" not in data:
            return

        with self._lock:
            _deep_merge(self.state, data["print"])
        self._notify()

    def _notify(self) -> None:
        if not self.on_update:
            return
        with self._lock:
            snapshot = dict(self.state)
        self.on_update(snapshot, self.connected)
