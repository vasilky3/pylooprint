"""Where the model sits on the bed.

Two answers to that question live here, because they are asked for different
reasons:

* :func:`determine_model_placement` scans the whole file and applies purge/wipe
  heuristics ported from Looprint.  It drives push-lane centring, and its
  output has to keep matching what the original tool produced.
* :func:`measure_extrusion_bounds` measures the isolated print body exactly,
  with no heuristics.  Collision checks need the truth, and the heuristics
  above discard whole regions of a bed-slinger plate.
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

#: Same axes, but signed - a bed-slinger plate starts at a negative X.
_SIGNED_X_RE = re.compile(r"X(-?[\d.]+)")
_SIGNED_Y_RE = re.compile(r"Y(-?[\d.]+)")
_SIGNED_E_RE = re.compile(r"E(-?[\d.]+)")


@dataclass(frozen=True)
class ExtrusionBounds:
    """Exact bounding box of the extruded model, in plate coordinates."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float

    def overlaps(self, min_x: float, max_x: float, min_y: float, max_y: float) -> bool:
        """True when this box intersects the given rectangle.

        Touching edges do not count as an overlap.
        """
        return (
            self.min_x < max_x
            and self.max_x > min_x
            and self.min_y < max_y
            and self.max_y > min_y
        )


def measure_extrusion_bounds(print_body: str) -> ExtrusionBounds | None:
    """Bounding box of every extruding move in the print body.

    Unlike :func:`determine_model_placement` this applies no purge or wipe
    heuristics: the machine start and end G-code has already been split off, so
    everything left that extrudes is model.  That makes it the only safe basis
    for a collision check - the heuristics discard, among other things, every
    point below X30, which is exactly where a collision would happen.

    ``None`` when the body contains nothing to measure.
    """
    xs: list[float] = []
    ys: list[float] = []

    for raw in print_body.split("\n"):
        line = raw.lstrip()
        if not (line.startswith("G1") or line.startswith("G0")):
            continue
        extrusion = _SIGNED_E_RE.search(line)
        if extrusion is None or _safe_float(extrusion.group(1)) <= 0:
            continue

        x_match = _SIGNED_X_RE.search(line)
        if x_match:
            xs.append(float(x_match.group(1)))
        y_match = _SIGNED_Y_RE.search(line)
        if y_match:
            ys.append(float(y_match.group(1)))

    if not xs or not ys:
        return None
    return ExtrusionBounds(min(xs), max(xs), min(ys), max(ys))


def extrusion_enters_zone(
    print_body: str, min_x: float, max_x: float, min_y: float, max_y: float
) -> tuple[float, float] | None:
    """A point where the model extrudes inside the rectangle, or ``None``.

    A bounding box is the wrong tool for this question: a plate whose model
    reaches the left edge in one place and the back edge in another has a box
    that covers the corner while leaving the corner itself empty.  This walks
    the actual moves instead.

    Whole *segments* are tested, not just their endpoints - diagonal infill can
    cross a small keep-out rectangle with both ends outside it.  Coordinates are
    modal, so the position is tracked across travel moves too.
    """
    x: float | None = None
    y: float | None = None

    for raw in print_body.split("\n"):
        line = raw.lstrip()
        if not (line.startswith("G1") or line.startswith("G0")):
            continue

        x_match = _SIGNED_X_RE.search(line)
        y_match = _SIGNED_Y_RE.search(line)
        next_x = float(x_match.group(1)) if x_match else x
        next_y = float(y_match.group(1)) if y_match else y

        extrusion = _SIGNED_E_RE.search(line)
        extruding = extrusion is not None and _safe_float(extrusion.group(1)) > 0
        if extruding and next_x is not None and next_y is not None:
            # Before the first positioned move the previous point is unknown, so
            # the move can only be judged by where it ends.
            start_x = x if x is not None else next_x
            start_y = y if y is not None else next_y
            hit = _segment_inside(start_x, start_y, next_x, next_y, min_x, max_x, min_y, max_y)
            if hit is not None:
                return hit

        x, y = next_x, next_y

    return None


def _segment_inside(
    x0: float, y0: float, x1: float, y1: float,
    min_x: float, max_x: float, min_y: float, max_y: float,
) -> tuple[float, float] | None:
    """Liang-Barsky clip: a point of the segment strictly inside the rectangle.

    Strictly, so that a move running exactly along an edge is not a collision -
    the same rule :meth:`ExtrusionBounds.overlaps` uses for touching edges.
    """
    dx, dy = x1 - x0, y1 - y0
    enter, leave = 0.0, 1.0

    for edge, distance in ((-dx, x0 - min_x), (dx, max_x - x0), (-dy, y0 - min_y), (dy, max_y - y0)):
        if edge == 0:
            if distance < 0:
                return None  # parallel to this edge, and on the outside of it
            continue
        crossing = distance / edge
        if edge < 0:
            if crossing > leave:
                return None
            enter = max(enter, crossing)
        else:
            if crossing < enter:
                return None
            leave = min(leave, crossing)

    if enter > leave:
        return None
    # The middle of the part that lies within the rectangle: on a genuine
    # crossing it is strictly inside, on a graze along an edge it is not.
    middle = (enter + leave) / 2
    point = (x0 + dx * middle, y0 + dy * middle)
    if min_x < point[0] < max_x and min_y < point[1] < max_y:
        return point
    return None


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
