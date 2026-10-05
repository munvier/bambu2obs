"""Entry point: python -m bambu2obs [-v]"""

import logging
import os
import sys

from dotenv import load_dotenv

from .client import BambuClient
from .server import Hub, make_server
from .summary import summarize

log = logging.getLogger("bambu2obs")


def main() -> int:
    load_dotenv()
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

    hub = Hub()
    client = BambuClient(
        host, serial, access_code,
        on_update=lambda state, connected: hub.publish(summarize(state, connected)),
    )
    server = make_server(hub, http_host, http_port)

    client.start()
    log.info("Overlay: http://localhost:%d  (OBS browser source)", http_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        client.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
