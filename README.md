# bambu2obs

OBS overlay showing the status of a Bambu Lab printer (P2S), read from its local MQTT broker.

## Printer prerequisites

- Printer and PC on the same network.
- **LAN mode** enabled and, depending on the firmware, **Developer mode** enabled
  (required for third-party tools to connect to the local MQTT broker).
- Collect: IP address, serial number, LAN access code.

## Installation

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # then fill in the values
```

## Running

```bash
python -m bambu2obs        # starts the MQTT client + the overlay server
python -m bambu2obs -v     # + dumps the raw MQTT messages
```

## Standalone executable (Windows)

No Python needed:

1. Download the latest `bambu2obs-vX.Y.Z-windows-x64.zip` from the
   [Releases](https://github.com/munvier/bambu2obs/releases) page and unzip it.
2. Copy `.env.example` to `.env` (same folder as `bambu2obs.exe`) and fill in the values.
3. Double-click `bambu2obs.exe` and keep the console window open.

The executable is not code-signed, so Windows SmartScreen may warn on first launch
("More info" > "Run anyway"). You can check the download against the published
`.sha256` file with `Get-FileHash bambu2obs-*.zip`.

To build it yourself:

```bash
pip install pyinstaller
pyinstaller --onefile --name bambu2obs --add-data "bambu2obs/web;bambu2obs/web" run.py
```

The result is `dist/bambu2obs.exe`. Pushing a `v*` tag builds and publishes it
automatically (see `.github/workflows/release.yml`).

## In OBS

Add a **Browser Source**:

- URL: `http://localhost:8765`
- Width `500`, height `220` (adjust if `scale` is changed)
- The background is transparent, no custom CSS needed.

Optional URL parameters:

| Parameter | Effect |
|---|---|
| `?scale=1.5` | enlarges the overlay |
| `?hideIdle=1` | hides the overlay when no print is in progress |

Example: `http://localhost:8765/?scale=1.5&hideIdle=1`

Other routes: `/state` (JSON of the summarized state), `/events` (SSE stream).

## Protocol (summary)

| | |
|---|---|
| Broker | `mqtts://<IP>:8883` (TLS, self-signed certificate) |
| Username / password | `bblp` / LAN access code |
| Status (subscribe) | `device/<SERIAL>/report` |
| Commands (publish) | `device/<SERIAL>/request` |
| Full state | `{"pushing": {"sequence_id": "1", "command": "pushall"}}` |

Reports often contain only the fields that changed: the client merges them
into `BambuClient.state`.

## License

[MIT](LICENSE)
