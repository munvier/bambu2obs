"""Entry point: python -m bambu2obs [-v]"""

import logging
import os
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

from .client import BambuClient
from .models import ModelStore
from .server import Hub, make_server
from .summary import summarize

log = logging.getLogger("bambu2obs")


def _base_dir() -> Path:
    # As a standalone executable, work next to the .exe rather than in the current directory.
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path.cwd()


def _load_env() -> None:
    if getattr(sys, "frozen", False):
        load_dotenv(_base_dir() / ".env")
    else:
        load_dotenv()


def main() -> int:
    _load_env()
    verbose = "-v" in sys.argv
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        host = os.environ["BAMBU_HOST"]
        serial = os.environ["BAMBU_SERIAL"]
        access_code = os.environ["BAMBU_ACCESS_CODE"]
    except KeyError as e:
        print(f"Missing variable: {e}. Copy .env.example to .env and fill it in.")
        return 1
    http_host = os.environ.get("BAMBU2OBS_HOST", "127.0.0.1")
    http_port = int(os.environ.get("BAMBU2OBS_PORT", "8765"))
    viewer_port = int(os.environ.get("BAMBU2OBS_VIEWER_PORT", "8766"))
    model_dir = _base_dir() / os.environ.get("BAMBU2OBS_MODEL_DIR", "models")
    model_dir.mkdir(parents=True, exist_ok=True)

    hub = Hub()
    client = BambuClient(
        host, serial, access_code,
        on_update=lambda state, connected: hub.publish(summarize(state, connected)),
    )
    models = ModelStore(model_dir)
    servers = []
    for port, index in ((http_port, "overlay.html"), (viewer_port, "viewer.html")):
        try:
            servers.append(make_server(hub, models, http_host, port, index))
        except OSError as e:
            print(f"Cannot listen on {http_host}:{port} ({e}). Is bambu2obs already running?")
            return 1

    client.start()
    log.info("Overlay:   http://localhost:%d  (OBS browser source)", http_port)
    log.info("3D viewer: http://localhost:%d  (OBS browser source)", viewer_port)
    log.info("Models:    drop a .3mf or .stl into %s", model_dir)
    for server in servers[1:]:
        threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        servers[0].serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
        for server in servers:
            server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
