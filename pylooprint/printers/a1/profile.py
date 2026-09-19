"""Bambu Lab A1 - not supported yet.

This is the stub a new printer starts from.  It is registered and detected, so a
plate sliced for an A1 is recognised and refused with a clear message instead of
being treated as something else.  Making it work means:

* an end-code splice like :class:`~pylooprint.printers.a1mini.A1MiniProfile`'s
  (``build_machine_code`` / ``patch_slicer_end_code``), checked against a real
  exported end code - the A1's may not be anchored on the same lines;
* measuring the eject geometry on the machine: the park height, the blade,
  the bumper offset, the keep-out corner the toolhead comes down in;
* a looping Orca profile under ``profiles/a1/`` that prints the purge wall, and
  ``purge_wall_x`` / ``purge_sweep_y`` to match it.

The bed and sweep figures below are the machine's known dimensions.
"""

from __future__ import annotations

from ...core.structure import GcodeStructure
from ...errors import LooprintError
from ..base import BedBounds, EndCodeContext, MachineCode
from ..bedslinger import BedSlingerProfile


class A1Profile(BedSlingerProfile):
    key = "a1"
    name = "A1"
    model_ids = ("N2S",)
    bed_bounds = BedBounds(min_x=-48, max_x=256, min_y=0, max_y=262)
    m190_repeat = 45

    push_height_factor = 0.7
    push_min_model_height = 6.0
    push_min_z = 0.2
    blade_width = 55.0
    blade_overlap = 0.5

    y_forward = 262
    wiggle_x_left = -48
    wiggle_x_right = 256
    wiggle_y_positions = (210, 165, 120, 75, 30, 0)
    wiggle_final_line = "G1 Y262 F2000\t;push bed forward one last time\n"

    def build_machine_code(self, structure: GcodeStructure, context: EndCodeContext) -> MachineCode:
        raise LooprintError(
            "A1: the eject sequence has not been written yet - only the A1 Mini is supported"
        )
