# bambu2obs

OBS overlays for a Bambu Lab printer (P2S): a status card and a rotating 3D view of the
model being printed, driven by the printer's local MQTT broker.

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
python -m bambu2obs        # starts the MQTT client + the two overlay servers
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

## OBS sources

The program serves two pages, each on its own port, so each can be added to OBS as a
separate **Browser Source**. Both have a transparent background (no custom CSS needed).

| Page | Address | Port setting (`.env`) | Suggested size |
|---|---|---|---|
| Status overlay | `http://localhost:8765` | `BAMBU2OBS_PORT` | `500` x `220` |
| 3D viewer | `http://localhost:8766` | `BAMBU2OBS_VIEWER_PORT` | `500` x `500` |

Parameters are appended to the address: the first one after `?`, the next ones after `&`,
e.g. `http://localhost:8765/?scale=1.5&hideIdle=1`. All of them are optional.

If OBS runs on another PC, set `BAMBU2OBS_HOST=0.0.0.0` in `.env` and replace
`localhost` with the IP of the PC running bambu2obs.

### Port 8765: status overlay

Address: `http://localhost:8765`

Shows the print state, job name, progress, remaining time, estimated end time, layer,
nozzle / bed temperatures and the AMS slots.

| Parameter | Default | Effect |
|---|---|---|
| `scale=1.5` | `1` | Enlarges the overlay. Multiply the source width and height by the same factor. |
| `hideIdle=1` | off | Hides the overlay when no print is in progress. |
| `color=ff8800` | filament colour | Progress bar colour: hex without `#` (`ff8800`, `f80`) or a CSS name (`orange`). |

Example: `http://localhost:8765/?scale=1.5&hideIdle=1&color=ff8800`

### Port 8766: 3D viewer

Address: `http://localhost:8766`

Shows the model rotating and filling up layer by layer in the colour of the active
filament; the part not printed yet is drawn as a translucent ghost.

The printer does not expose the model over MQTT, so you provide it: drop the `.3mf`
(Bambu Studio project) or `.stl` into the `models/` folder next to the program
(`BAMBU2OBS_MODEL_DIR` to change it). The most recently modified file is displayed, and
the page picks up a new file within a few seconds, no restart needed. For multi-plate
projects only the plate being printed is shown. Sliced-only `.gcode.3mf` files contain
no mesh and cannot be displayed.

| Parameter | Default | Effect |
|---|---|---|
| `speed=2` | `1` | Rotation speed. `1` is one turn every 20 s, `0` keeps the model still. |
| `progress=0` | on | Always shows the whole model instead of filling it up. |
| `fill=0.5` | off | Forces a progress from `0` to `1`, handy to preview the look without printing. |
| `hideIdle=1` | off | Hides the model when no print is in progress. |
| `color=ff8800` | filament colour | Model colour: hex without `#` (`ff8800`, `f80`) or a CSS name (`orange`). |

Example: `http://localhost:8766/?speed=2&color=ff8800&hideIdle=1`

The viewer loads three.js from a CDN, so the PC running OBS needs internet access.

### Other addresses

Available on both ports:

| Address | Content |
|---|---|
| `/overlay.html` | The status overlay |
| `/viewer.html` | The 3D viewer |
| `/state` | Summarized printer state, as JSON |
| `/events` | Live state updates (Server-Sent Events) |
| `/model.json` | Name and folder of the model currently displayed |
| `/model.bin` | The model's triangles, as loaded by the viewer |

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
