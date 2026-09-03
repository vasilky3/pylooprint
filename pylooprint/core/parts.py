"""The separate parts sitting on the plate, and the box each one occupies.

The rest of the code only ever asks about the plate as a whole: where the model
sits (:func:`~pylooprint.core.placement.determine_model_placement`) and what
single box everything fits in
(:func:`~pylooprint.core.placement.measure_extrusion_bounds`).  Neither answers
"how many parts are on this plate, and where is each one" - which is what an
operator wants to see before starting an unattended looping run.

Parts are found from the *geometry*, not from the slicer's object markers: what
matters is which lumps of plastic are physically separate, and one slicer object
can hold several of them.  The extruded moves are dropped into a grid of
``gap``-sized cells, and cells that touch belong to the same part, so:

* two extruded points closer together than ``gap`` always land in the same part;
* points further apart than ``2 * gap`` are never merged directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator

from .placement import ExtrusionSegment, iter_extrusion_segments

#: How far apart two extrusions have to be before they count as separate parts.
PART_GAP_TOLERANCE = 4.0

#: Features that are not a part, or that would fuse several parts into one: the
#: skirt is a single loop drawn around *everything* on the plate, a brim shared
#: between two neighbours joins them the same way, and the prime tower is waste
#: rather than a part.  A file without ``; FEATURE:`` markers skips nothing.
NON_PART_FEATURES = ("Skirt", "Brim", "Prime tower")

_Cell = tuple[int, int]


@dataclass(frozen=True)
class PartBounds:
    """Axis-aligned box one part occupies, in plate coordinates."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def depth(self) -> float:
        return self.max_y - self.min_y

    @property
    def height(self) -> float:
        return self.max_z - self.min_z


def find_parts(print_body: str, *, gap: float = PART_GAP_TOLERANCE) -> list[PartBounds]:
    """Every separate part in the print body, front-left first.

    The print body has already been split off from the machine G-code, so
    everything left that extrudes is model - no purge or wipe heuristics are
    needed here, only the features listed in :data:`NON_PART_FEATURES`.
    """
    cells = _occupied_cells(print_body, gap)
    if not cells:
        return []

    merge = _CellMerge(cells)
    for cell in cells:
        for neighbour in _neighbours(cell):
            if neighbour in cells:
                merge.union(cell, neighbour)

    parts: dict[_Cell, _Box] = {}
    for cell, box in cells.items():
        root = merge.find(cell)
        grown = parts.get(root)
        if grown is None:
            parts[root] = box
        else:
            grown.absorb(box)

    return sorted(
        (box.as_bounds() for box in parts.values()),
        key=lambda part: (part.min_x, part.min_y),
    )


def _occupied_cells(print_body: str, gap: float) -> dict[_Cell, _Box]:
    """Grid cells the model extrudes into, with the extent of each.

    Every move is sampled at half a cell, so a long infill line cannot step over
    one - and consecutive samples are then always in the same cell or a
    neighbouring one, which is what lets the neighbour pass alone rebuild the
    move's own continuity.
    """
    cells: dict[_Cell, _Box] = {}

    for segment in _part_segments(print_body):
        span = max(abs(segment.x1 - segment.x0), abs(segment.y1 - segment.y0))
        steps = int(span / (gap / 2)) + 1
        for step in range(steps + 1):
            travelled = step / steps
            x = segment.x0 + (segment.x1 - segment.x0) * travelled
            y = segment.y0 + (segment.y1 - segment.y0) * travelled
            cell = (int(x // gap), int(y // gap))
            box = cells.get(cell)
            if box is None:
                cells[cell] = _Box(x, y, segment.z)
            else:
                box.add(x, y, segment.z)

    return cells


def _part_segments(print_body: str) -> Iterator[ExtrusionSegment]:
    """Extruding moves that belong to a part, skipping the fusing features."""
    for segment in iter_extrusion_segments(print_body):
        if segment.feature not in NON_PART_FEATURES:
            yield segment


def _neighbours(cell: _Cell) -> Iterator[_Cell]:
    """The eight cells around this one."""
    x, y = cell
    for step_x in (-1, 0, 1):
        for step_y in (-1, 0, 1):
            if step_x or step_y:
                yield x + step_x, y + step_y


class _Box:
    """The extent of the points that fell into one cell, or one whole part."""

    __slots__ = ("min_x", "max_x", "min_y", "max_y", "min_z", "max_z")

    def __init__(self, x: float, y: float, z: float) -> None:
        self.min_x = self.max_x = x
        self.min_y = self.max_y = y
        self.min_z = self.max_z = z

    def add(self, x: float, y: float, z: float) -> None:
        self.min_x = min(self.min_x, x)
        self.max_x = max(self.max_x, x)
        self.min_y = min(self.min_y, y)
        self.max_y = max(self.max_y, y)
        self.min_z = min(self.min_z, z)
        self.max_z = max(self.max_z, z)

    def absorb(self, other: _Box) -> None:
        self.add(other.min_x, other.min_y, other.min_z)
        self.add(other.max_x, other.max_y, other.max_z)

    def as_bounds(self) -> PartBounds:
        return PartBounds(self.min_x, self.max_x, self.min_y, self.max_y, self.min_z, self.max_z)


class _CellMerge:
    """Union-find over the occupied cells."""

    def __init__(self, cells: dict[_Cell, _Box]) -> None:
        self._parent: dict[_Cell, _Cell] = {cell: cell for cell in cells}

    def find(self, cell: _Cell) -> _Cell:
        parent = self._parent
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = parent[cell]
        return cell

    def union(self, one: _Cell, other: _Cell) -> None:
        root, other_root = self.find(one), self.find(other)
        if root != other_root:
            self._parent[other_root] = root
