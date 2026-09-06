"""Where the printer leaves the head when an ordinary print finishes.

The slicer ends every file the same way: lift the gantry clear of the print,
then park - on the A1 Mini ``G1 X-13 Y180``, with the Z it lifted to following
the part (its height plus 100 mm, capped at the machine's own ceiling).

Looping replaces that whole stretch of the end code with the eject sequence, so
without carrying these moves over the job would finish wherever the sweep left
the head: a millimetre above the plate.  Both halves are read straight out of
the file rather than written here, which is what makes the parked position the
*same* one an unlooped print reaches, on any plate.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The line the slicer lowers the Z current on, just before it lifts.
LIFT_AFTER = "M17 Z0.4 ; lower z motor current to reduce impact if there is something in the bottom"
#: What brackets the park itself: current restored, then the reset tail.
PARK_AFTER = "M17 R ; restore z current"
PARK_BEFORE = "M220 S100  ; Reset feedrate magnitude"


@dataclass(frozen=True)
class SlicerPark:
    """The slicer's own end-of-print moves, as they appear in the file."""

    #: ``G1 Z…`` moves that lift the gantry clear of the finished part.
    lift: str
    #: What it then does to park - travel, and the mode it leaves behind.
    moves: str


def read_slicer_park(slicer_end_code: str) -> SlicerPark | None:
    """The lift and park an ordinary print of this plate would end with.

    ``None`` when the end code is not shaped like this, which leaves the caller
    doing whatever it did before rather than guessing at a position.
    """
    moves = _between(slicer_end_code, PARK_AFTER, PARK_BEFORE)
    if moves is None:
        return None
    return SlicerPark(lift=lift_moves(slicer_end_code), moves=moves)


def lift_moves(slicer_end_code: str) -> str:
    """The ``G1 Z…`` moves the slicer lifts with, de-indented.

    They sit in a ``{if}`` block in the slicer's template, so they arrive
    indented; the block itself is gone by the time they are re-emitted.
    """
    start = slicer_end_code.find(LIFT_AFTER)
    if start == -1:
        return ""

    lifted: list[str] = []
    for line in slicer_end_code[start + len(LIFT_AFTER) :].split("\n"):
        stripped = line.strip()
        if stripped.startswith("G1 Z"):
            lifted.append(stripped)
        elif lifted and stripped:
            break
    return "\n".join(lifted)


def _between(text: str, after: str, before: str) -> str | None:
    """The commands between two anchor lines, blank lines dropped."""
    start = text.find(after)
    if start == -1:
        return None
    end = text.find(before, start)
    if end == -1:
        return None
    lines = [line.strip() for line in text[start + len(after) : end].split("\n")]
    return "\n".join(line for line in lines if line)
