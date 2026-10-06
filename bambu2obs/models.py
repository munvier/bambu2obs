"""Finds the model to display in the local folder and turns it into a triangle soup."""

import logging
import threading
import xml.etree.ElementTree as ET
import zipfile
from array import array
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

EXTENSIONS = (".3mf", ".stl")
P_PATH = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path"
IDENTITY = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0)
ROOT_MODEL = "3D/3dmodel.model"
MODEL_SETTINGS = "Metadata/model_settings.config"

# 3MF transforms are 4x3 affine matrices, row-major, applied to row vectors.
Transform = tuple[float, ...]


def _parse_transform(text: str | None) -> Transform:
    if not text:
        return IDENTITY
    values = tuple(float(v) for v in text.split())
    return values if len(values) == 12 else IDENTITY


def _compose(a: Transform, b: Transform) -> Transform:
    """Transform equivalent to applying a, then b."""
    out = []
    for r in range(4):
        row = a[r * 3:r * 3 + 3]
        for c in range(3):
            v = row[0] * b[c] + row[1] * b[3 + c] + row[2] * b[6 + c]
            if r == 3:
                v += b[9 + c]
            out.append(v)
    return tuple(out)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _parse_model_part(fp) -> tuple[dict[str, dict[str, Any]], list[tuple]]:
    """Returns (objects by id, build items) of one .model file of the archive."""
    objects: dict[str, dict[str, Any]] = {}
    build: list[tuple] = []
    cur: dict[str, Any] | None = None
    for event, el in ET.iterparse(fp, events=("start", "end")):
        tag = _local(el.tag)
        if event == "start":
            if tag == "object":
                cur = {"vertices": array("f"), "triangles": array("I"), "components": []}
                objects[el.get("id")] = cur
            continue
        if tag == "vertex" and cur is not None:
            cur["vertices"].extend((float(el.get("x")), float(el.get("y")), float(el.get("z"))))
        elif tag == "triangle" and cur is not None:
            cur["triangles"].extend((int(el.get("v1")), int(el.get("v2")), int(el.get("v3"))))
        elif tag == "component" and cur is not None:
            cur["components"].append(
                (el.get(P_PATH), el.get("objectid"), _parse_transform(el.get("transform")))
            )
        elif tag == "item":
            if el.get("printable", "1") != "0":
                build.append((el.get(P_PATH), el.get("objectid"), _parse_transform(el.get("transform"))))
        elif tag == "object":
            cur = None
        if tag in ("vertex", "triangle", "vertices", "triangles"):
            el.clear()  # keeps memory bounded on big meshes
    return objects, build


def _plate_instances(zf: zipfile.ZipFile, plate: int) -> set[tuple[str, int]] | None:
    """(object id, instance index) pairs placed on the given plate (Bambu Studio projects)."""
    if MODEL_SETTINGS not in zf.namelist():
        return None
    try:
        root = ET.fromstring(zf.read(MODEL_SETTINGS))
    except ET.ParseError:
        return None
    for plate_el in root.iter("plate"):
        meta = {m.get("key"): m.get("value") for m in plate_el.findall("metadata")}
        if meta.get("plater_id") != str(plate):
            continue
        instances = set()
        for inst in plate_el.iter("model_instance"):
            m = {x.get("key"): x.get("value") for x in inst.findall("metadata")}
            instances.add((m.get("object_id"), int(m.get("instance_id") or 0)))
        return instances
    return None


def _load_3mf(path: Path, plate: int | None) -> array:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        parts: dict[str, dict[str, dict[str, Any]]] = {}

        def part(name: str) -> dict[str, dict[str, Any]]:
            name = name.lstrip("/")
            if name not in parts:
                if name not in names:
                    parts[name] = {}
                else:
                    with zf.open(name) as fp:
                        parts[name] = _parse_model_part(fp)[0]
            return parts[name]

        if ROOT_MODEL not in names:
            raise ValueError("no 3D model in this file (sliced .gcode.3mf?)")
        with zf.open(ROOT_MODEL) as fp:
            parts[ROOT_MODEL], build = _parse_model_part(fp)

        wanted = _plate_instances(zf, plate) if plate else None
        seen: dict[str, int] = {}
        items = []
        for item in build:
            index = seen.get(item[1], 0)
            seen[item[1]] = index + 1
            items.append((item, (item[1], index)))
        selected = [item for item, key in items if wanted and key in wanted]
        if not selected:
            selected = [item for item, _ in items]

        out = array("f")

        def emit(part_name: str, object_id: str, transform: Transform, depth: int = 0) -> None:
            obj = part(part_name).get(object_id)
            if obj is None or depth > 8:
                return
            vertices = obj["vertices"]
            if vertices:
                m = transform
                moved = array("f", bytes(len(vertices) * 4))
                for i in range(0, len(vertices), 3):
                    x, y, z = vertices[i], vertices[i + 1], vertices[i + 2]
                    moved[i] = x * m[0] + y * m[3] + z * m[6] + m[9]
                    moved[i + 1] = x * m[1] + y * m[4] + z * m[7] + m[10]
                    moved[i + 2] = x * m[2] + y * m[5] + z * m[8] + m[11]
                for index in obj["triangles"]:
                    out.extend(moved[index * 3:index * 3 + 3])
            for comp_path, comp_id, comp_transform in obj["components"]:
                emit(comp_path or part_name, comp_id, _compose(comp_transform, transform), depth + 1)

        for item_path, object_id, transform in selected:
            emit(item_path or ROOT_MODEL, object_id, transform)

    if not out:
        raise ValueError("no 3D model in this file (sliced .gcode.3mf?)")
    return out


class ModelStore:
    """Serves the most recently modified model of a folder, converted once and cached."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._lock = threading.Lock()
        self._cache_key: tuple | None = None
        self._cache: tuple[str, bytes] | None = None

    def latest(self) -> Path | None:
        try:
            files = [
                p for p in self.folder.iterdir()
                if p.is_file() and p.suffix.lower() in EXTENSIONS
            ]
        except OSError:
            return None
        return max(files, key=lambda p: p.stat().st_mtime, default=None)

    def info(self) -> dict[str, Any]:
        path = self.latest()
        if path is None:
            return {"name": None, "version": None, "folder": str(self.folder)}
        stat = path.stat()
        return {
            "name": path.name,
            "version": f"{path.name}:{stat.st_mtime_ns}:{stat.st_size}",
            "folder": str(self.folder),
        }

    def data(self, plate: int | None) -> tuple[str, bytes] | None:
        """(format, payload): 'stl' is the raw file, 'raw' is float32 xyz triplets, 3 per triangle."""
        path = self.latest()
        if path is None:
            return None
        if path.suffix.lower() == ".stl":
            plate = None
        stat = path.stat()
        key = (str(path), stat.st_mtime_ns, stat.st_size, plate)
        with self._lock:
            if key != self._cache_key:
                log.info("Loading model %s", path.name)
                if path.suffix.lower() == ".stl":
                    result = ("stl", path.read_bytes())
                else:
                    result = ("raw", _load_3mf(path, plate).tobytes())
                self._cache_key, self._cache = key, result
            return self._cache
