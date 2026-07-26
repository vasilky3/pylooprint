"""Where the model sits on the bed.

Common analysis step.  The extrusion moves are scanned for their X/Y extent,
which gives the CoreXY printers their push lanes and the bed slingers a
fallback model centre when the slicer did not record one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MIN_POINTS_REQUIRED = 50
MAX_DATA_POINTS = 10000
MAX_LINES_TO_PARSE = 100000
Z_FILTER_THRESHOLD = 4.0

#: Bed zones used to classify a model as left / centre / right.
PUSH_LEFT_BOUNDARY = 90
PUSH_RIGHT_BOUNDARY = 166
EDGE_THRESHOLD = 10

_X_RE = re.compile(r"X([\d.]+)")
_Y_RE = re.compile(r"Y([\d.]+)")
_Z_RE = re.compile(r"Z([\d.]+)")
_E_RE = re.compile(r"E([\d.-]+)")


@dataclass(frozen=True)
class ModelPlacement:
    """Bounding box of the printed model plus the chosen push direction."""

    direction: str
    min_x: float
    max_x: float
    min_y: float | None = None
    max_y: float | None = None

    def as_bounds(self) -> dict[str, float]:
        bounds: dict[str, float] = {"minX": self.min_x, "maxX": self.max_x}
        if self.min_y is not None and self.max_y is not None:
            bounds["minY"] = self.min_y
            bounds["maxY"] = self.max_y
        return bounds


def determine_model_placement(
    gcode: str,
    bed_min_x: float,
    bed_max_x: float,
    bed_min_y: float,
    bed_max_y: float,
) -> ModelPlacement:
    """Scan extrusion moves and classify the model's position on the bed."""
    x_coords, y_coords = _collect_coordinates(gcode, bed_min_y, bed_max_y)

    if len(x_coords) < MIN_POINTS_REQUIRED:
        return ModelPlacement("center", 0.0, 256.0)

    inside = [x for x in x_coords if bed_min_x < x < bed_max_x]
    if not inside:
        return ModelPlacement("center", 0.0, 256.0)

    min_x, max_x = min(inside), max(inside)
    min_y = min(y_coords) if y_coords else None
    max_y = max(y_coords) if y_coords else None

    return ModelPlacement(_classify(min_x, max_x), min_x, max_x, min_y, max_y)


def _collect_coordinates(gcode: str, bed_min_y: float, bed_max_y: float) -> tuple[list[float], list[float]]:
    x_coords: list[float] = []
    y_coords: list[float] = []

    for index, raw in enumerate(gcode.split("\n")):
        if index >= MAX_LINES_TO_PARSE:
            break
        line = raw.strip()
        if not (line.startswith("G0") or line.startswith("G1")):
            continue
        if "X" not in line or "Y" not in line or "E" not in line:
            continue

        x_match = _X_RE.search(line)
        if not x_match:
            continue
        y_match = _Y_RE.search(line)
        z_match = _Z_RE.search(line)
        e_match = _E_RE.search(line)

        z_value = float(z_match.group(1)) if z_match else 0.0
        e_value = _safe_float(e_match.group(1)) if e_match else 0.0
        if not (z_value > Z_FILTER_THRESHOLD or e_value > 0):
            continue

        x_value = float(x_match.group(1))
        y_value = float(y_match.group(1)) if y_match else None
        if not _is_purge_or_wipe(index, x_value, y_value, z_value):
            x_coords.append(x_value)

        if y_value is not None and bed_min_y <= y_value <= bed_max_y:
            y_coords.append(y_value)

        if len(x_coords) > MAX_DATA_POINTS:
            break

    return x_coords, y_coords


def _is_purge_or_wipe(index: int, x: float, y: float | None, z: float) -> bool:
    """Filter out prime lines, nozzle wipes and start-code travel moves."""
    negative_z = z < 0
    high_y = y is not None and y > 250
    wipe_x = index < 5000 and any(abs(x - candidate) < 1 for candidate in (65, 100, 165))
    centre_wipe = index < 5000 and abs(x - 128) < 1 and (high_y or negative_z)
    purge_x = (index < 2000 and x < 50) or x < 30
    start_code_x = index < 5000 and x > 200
    return negative_z or high_y or wipe_x or centre_wipe or purge_x or start_code_x


def _classify(min_x: float, max_x: float) -> str:
    if min_x > PUSH_RIGHT_BOUNDARY:
        return "right"
    if max_x < PUSH_LEFT_BOUNDARY:
        return "left"

    total_width = max_x - min_x
    width_left = max(0.0, min(max_x, PUSH_LEFT_BOUNDARY) - min_x)
    width_right = max(0.0, max_x - max(min_x, PUSH_RIGHT_BOUNDARY))
    width_centre = total_width - width_left - width_right

    centre_dominant = (
        width_centre > width_left and width_centre > width_right and width_centre > 30
    ) or (width_left == 0 and width_right == 0 and width_centre > 0)
    if centre_dominant:
        return "center"
    if width_right > width_left + EDGE_THRESHOLD:
        return "right"
    if width_left > width_right + EDGE_THRESHOLD:
        return "left"
    if width_right > width_left:
        return "right"
    if width_left > width_right:
        return "left"
    return "center"


def _safe_float(text: str) -> float:
    try:
        return float(text)
    except ValueError:
        return 0.0
