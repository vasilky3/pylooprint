"""The contract every printer profile implements.

Everything common lives in :mod:`pylooprint.core`; a profile supplies only what
differs between machines - the bed envelope, how the parts are pushed off, and
how the slicer's machine G-code is turned into one loop's start and end code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib import resources
from typing import Sequence

from ..core.parking import SlicerPark
from ..core.parts import PartBounds
from ..core.push_plan import PushLine
from ..core.structure import GcodeStructure
from ..settings import LoopSettings

_TEMPLATE_PACKAGE = "pylooprint.printers"

#: Markers bracketing the pre-push beep, so it can be located in a finished file.
BEEP_START = ";======= PYLOOPRINT RELEASE BEEP ======="
BEEP_END = ";======= END PYLOOPRINT RELEASE BEEP ======="


@dataclass(frozen=True)
class BedBounds:
    """Reachable bed envelope in millimetres."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float


@dataclass(frozen=True)
class MachineCode:
    """The machine G-code one loop is wrapped in."""

    start_code: str
    end_code: str
    #: The end code for the last loop, when it differs - the head parks there.
    #: ``None`` leaves every loop ending the same way.
    final_end_code: str | None = None
    #: Notes for the user.
    warnings: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class EndCodeContext:
    """What the end-code generator needs from the sliced file."""

    settings: LoopSettings
    #: The separate parts on the plate, in report order.  Empty when the body
    #: could not be measured, which sends the push-off back to its one-line form.
    parts: tuple[PartBounds, ...] = ()
    #: The push the pipeline planned from those parts - the same lines the report
    #: names.  Empty sends a bed slinger back to planning its own.
    push_lines: tuple[PushLine, ...] = ()
    #: Where an ordinary print of this plate would leave the head, read out of
    #: the slicer's own end code.  ``None`` when that file is shaped otherwise.
    slicer_park: SlicerPark | None = None
    #: Height of the tallest thing printed, from the file header.
    model_height: float = 0.0
    #: X of the middle of everything printed - where the one-line push aims when
    #: the parts are unknown.
    centre_x: float = 0.0


def load_template(relative_path: str) -> str:
    """Read a G-code template shipped inside :mod:`pylooprint.printers`."""
    return resources.files(_TEMPLATE_PACKAGE).joinpath(relative_path).read_text(encoding="utf-8")


class PrinterProfile(ABC):
    """A single printer family.

    Adding a printer: a package under ``printers/`` with a subclass of this (or
    of :class:`~pylooprint.printers.bedslinger.BedSlingerProfile` for a machine
    whose bed moves in Y), one entry in the registry in ``printers/__init__.py``,
    its model id in ``detection.py``, and a looping Orca profile under
    ``profiles/<key>/``.  ``printers/a1/`` is the stub to start from.
    """

    #: CLI name (``--printer a1mini``).
    key: str
    name: str
    #: ``printer_model_id`` values found in ``Metadata/slice_info.config``.
    model_ids: tuple[str, ...] = ()
    bed_bounds: BedBounds
    #: The blade that pushes a part off: how wide the toolhead sweeps, in mm,
    #: and how much of that width has to sit over a part to carry it.  Their
    #: product is how far from a line a part may stand and still be pushed.
    blade_width: float
    blade_overlap: float

    def apply_temp_offset(self, temp: int) -> int:
        """Bed temperature to command for a requested cool-down temperature."""
        return temp

    def release_beep(self) -> str:
        """One short tone, emitted immediately before the push-off.

        The machine has been standing still through the cool-down, so the beep
        is the only warning that it is about to move again and throw the part
        off the plate.  ``M1006`` is the tone macro the slicer's own finish
        sound uses.
        """
        return "\n".join(
            [
                BEEP_START,
                "M400 ; wait for all motion to complete",
                "M1006 S1",
                "M1006 A0 B20 L100 C44 D20 M100 E44 F20 N100",
                "M1006 W",
                BEEP_END,
            ]
        )

    def push_plan(self, parts: Sequence[PartBounds], print_body: str = "") -> list[PushLine]:
        """The lines the blade runs to sweep this plate, left to right.

        Called once per build: the plan is reported and carried in the context,
        so the report and the G-code cannot describe different pushes.  Empty
        for a profile whose push-off does not follow the parts.

        ``print_body`` lets a profile measure against the G-code itself rather
        than against the parts' boxes; it is only handed over when something in
        the plan needs that accuracy.
        """
        return []

    def check_eject_clearance(self, print_body: str) -> None:
        """Refuse the build if the model fouls this printer's eject sequence.

        The default accepts anything.  A profile whose eject sequence brings
        the toolhead down onto the plate overrides this and raises
        :class:`~pylooprint.errors.UnsafeEjectZoneError`.
        """

    @abstractmethod
    def build_machine_code(self, structure: GcodeStructure, context: EndCodeContext) -> MachineCode:
        """Produce the start and end code that wrap one loop.

        ``structure.slicer_start_code`` / ``structure.slicer_end_code`` are the
        slicer's own machine G-code; the profile decides what to keep of them.
        """
