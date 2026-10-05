"""Local HTTP server: serves the overlay and pushes state as Server-Sent Events."""

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

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


def make_handler(hub: Hub) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            log.debug("%s - %s", self.address_string(), format % args)

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path in ("/", "/overlay.html"):
                self._send_file(WEB_DIR / "overlay.html", "text/html; charset=utf-8")
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


def make_server(hub: Hub, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(hub))
    server.daemon_threads = True
    return server
