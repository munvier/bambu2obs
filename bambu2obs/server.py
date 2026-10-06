"""Local HTTP servers: serve the overlay / 3D viewer pages and push state as Server-Sent Events."""

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from .models import ModelStore

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"
KEEPALIVE_S = 15


class Hub:
    """Last known state + wakes SSE clients on every update."""

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._version = 0
        self._payload = json.dumps({"connected": False})

    def publish(self, data: dict[str, Any]) -> None:
        payload = json.dumps(data)
        with self._cond:
            if payload == self._payload:
                return
            self._payload = payload
            self._version += 1
            self._cond.notify_all()

    def current(self) -> tuple[int, str]:
        with self._cond:
            return self._version, self._payload

    def wait(self, after: int) -> tuple[int, str] | None:
        with self._cond:
            if not self._cond.wait_for(lambda: self._version != after, timeout=KEEPALIVE_S):
                return None
            return self._version, self._payload


def make_handler(hub: Hub, models: ModelStore, index: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            log.debug("%s - %s", self.address_string(), format % args)

        def do_GET(self) -> None:
            url = urlsplit(self.path)
            path = url.path
            if path == "/":
                path = "/" + index
            if path in ("/overlay.html", "/viewer.html"):
                self._send_file(WEB_DIR / path[1:], "text/html; charset=utf-8")
            elif path == "/model.json":
                self._send_bytes(json.dumps(models.info()).encode(), "application/json")
            elif path == "/model.bin":
                self._send_model(parse_qs(url.query).get("plate", [""])[0])
            elif path == "/state":
                self._send_bytes(hub.current()[1].encode(), "application/json")
            elif path == "/events":
                self._stream_events()
            else:
                self.send_error(404)

        def _send_bytes(self, body: bytes, content_type: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_file(self, path: Path, content_type: str) -> None:
            self._send_bytes(path.read_bytes(), content_type)

        def _send_model(self, plate: str) -> None:
            try:
                result = models.data(int(plate) if plate.isdigit() else None)
            except Exception as e:
                log.warning("Cannot load model: %s", e)
                self.send_error(422, str(e))
                return
            if result is None:
                self.send_error(404)
                return
            fmt, body = result
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Model-Format", fmt)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _stream_events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            version, payload = hub.current()
            try:
                self._write_event(payload)
                while True:
                    update = hub.wait(version)
                    if update is None:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        continue
                    version, payload = update
                    self._write_event(payload)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _write_event(self, payload: str) -> None:
            self.wfile.write(f"data: {payload}\n\n".encode())
            self.wfile.flush()

    return Handler


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, SO_REUSEADDR lets a second instance silently bind the same port.
    allow_reuse_address = os.name != "nt"


def make_server(hub: Hub, models: ModelStore, host: str, port: int, index: str) -> ThreadingHTTPServer:
    """index is the page served at "/": every other route is available on both servers."""
    return _Server((host, port), make_handler(hub, models, index))
