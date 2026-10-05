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
