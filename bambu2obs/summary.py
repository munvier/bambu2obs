"""Reduce the raw MQTT state to the fields the overlay needs."""

from typing import Any

EXTERNAL_SPOOL = 254
NO_TRAY = 255


def _color(hex_rgba: str | None) -> str | None:
    """'FEC600FF' -> '#FEC600'"""
    if not hex_rgba or len(hex_rgba) < 6:
        return None
    return "#" + hex_rgba[:6]


def _trays(state: dict[str, Any]) -> list[dict[str, Any]]:
    trays = []
    for unit in state.get("ams", {}).get("ams", []):
        for tray in unit.get("tray", []):
            idx = int(unit.get("id", 0)) * 4 + int(tray.get("id", 0))
            trays.append({
                "index": idx,
                "type": tray.get("tray_type") or None,
                "name": tray.get("tray_sub_brands") or tray.get("tray_type") or None,
                "color": _color(tray.get("tray_color")) if tray.get("tray_type") else None,
                "remain": tray.get("remain", -1),
            })
    return trays


def _active_tray(state: dict[str, Any]) -> int | None:
    try:
        now = int(state.get("ams", {}).get("tray_now", NO_TRAY))
    except (TypeError, ValueError):
        return None
    return None if now == NO_TRAY else now


def summarize(state: dict[str, Any], connected: bool) -> dict[str, Any]:
    trays = _trays(state)
    active = _active_tray(state)
    active_tray = next((t for t in trays if t["index"] == active), None)
    if active == EXTERNAL_SPOOL:
        ext = (state.get("vir_slot") or [{}])[0] or state.get("vt_tray", {})
        active_tray = {
            "index": EXTERNAL_SPOOL,
            "type": ext.get("tray_type") or None,
            "name": ext.get("tray_sub_brands") or ext.get("tray_type") or "External spool",
            "color": _color(ext.get("tray_color")),
            "remain": -1,
        }

    return {
        "connected": connected,
        "state": state.get("gcode_state"),
        "name": state.get("subtask_name"),
        "percent": state.get("mc_percent"),
        "remaining_min": state.get("mc_remaining_time"),
        "layer": state.get("layer_num"),
        "total_layers": state.get("total_layer_num"),
        "nozzle": state.get("nozzle_temper"),
        "nozzle_target": state.get("nozzle_target_temper"),
        "bed": state.get("bed_temper"),
        "bed_target": state.get("bed_target_temper"),
        "speed_level": state.get("spd_lvl"),
        "trays": trays,
        "active_tray": active_tray,
    }
