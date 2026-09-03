"""The contract every printer profile implements.

Everything that is *common* lives in :mod:`pylooprint.core`; a profile only
supplies what genuinely differs between machines - the start-code template, the
end-code (push-off) sequence, the bed envelope, the cool-down handling and the
temperature offset.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from importlib import resources
from typing import Mapping, Sequence

from ..core.parts import PartBounds
from ..core.push_plan import PushLine
from ..core.structure import GcodeStructure
from ..core.template import render_start_code
from ..settings import LoopSettings

_TEMPLATE_PACKAGE = "pylooprint.printers.templates"

#: Markers bracketing the pre-push beep, so it can be located in a finished file.
BEEP_START = ";======= LOOPRINT RELEASE BEEP ======="
BEEP_END = ";======= END LOOPRINT RELEASE BEEP ======="


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
    #: Notes for the user - e.g. that a profile fell back to the templates.
    warnings: tuple[str, ...] = field(default=())


@dataclass(frozen=True)
class EndCodeContext:
    """What the end-code generator needs from the sliced file.

    The model height and centre are *not* here: profiles emit
    ``{max_layer_z ...}`` and ``{first_layer_center_no_wipe_tower[n]}`` verbatim
    and the pipeline resolves them afterwards, exactly once, for every printer.
    """

    settings: LoopSettings
    #: Model bounding box, when placement detection produced one.
    model_min_x: float | None = None
    model_max_x: float | None = None
    #: The separate parts on the plate, in report order.  Empty when the body
    #: could not be measured, which sends the push-off back to its one-line form.
    parts: tuple[PartBounds, ...] = ()
    #: Side of the bed the model sits on: ``left`` / ``center`` / ``right``.
    direction: str = "center"


def load_template(name: str) -> str:
    """Read a G-code template shipped with the package."""
    return resources.files(_TEMPLATE_PACKAGE).joinpath(name).read_text(encoding="utf-8")


class PrinterProfile(ABC):
    """A single printer family."""

    key: str
    name: str
    #: ``printer_model_id`` values found in ``Metadata/slice_info.config``.
    model_ids: tuple[str, ...] = ()
    bed_bounds: BedBounds
    #: Difference between the requested and the commanded bed temperature.
    temp_offset: int = 0
    #: How many ``M190`` lines are needed to outlast the firmware's wait timeout.
    m190_repeat: int = 1
    #: Start-code template shipped for this machine.
    start_template_name: str
    #: The blade that pushes a part off: how wide the toolhead sweeps, in mm,
    #: and how much of that width has to sit over a part to carry it.  Their
    #: product is how far from a line a part may stand and still be pushed.
    blade_width: float
    blade_overlap: float

    def apply_temp_offset(self, temp: int) -> int:
        """Bed temperature to actually command for a requested cool-down temp."""
        return temp

    def cooldown_block(self, temp: int) -> str:
        """The repeated ``M190`` wait that holds the print until it releases."""
        return "\n".join([f"M190 S{self.apply_temp_offset(temp)}"] * self.m190_repeat)

    def start_code(self) -> str:
        """Raw start-code template, before variable substitution."""
        return load_template(self.start_template_name)

    def release_beep(self) -> str:
        """One short tone, emitted immediately before the push-off.

        Every profile uses it: the machine has been standing still through the
        cool-down, so the beep is the only warning that it is about to move
        again and throw the part off the plate.

        ``M1006`` is the same tone macro the slicer's own finish sound uses -
        one note instead of a tune.  A firmware that does not know it ignores
        the block, which costs nothing but the sound.
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

    @abstractmethod
    def end_code(self, context: EndCodeContext) -> str:
        """Cool-down and push-off sequence appended after every loop."""

    def end_code_warnings(self, context: EndCodeContext) -> tuple[str, ...]:
        """Notes the end-code generator produced - e.g. auto-adjusted push lanes."""
        return ()

    def push_plan(self, parts: Sequence[PartBounds]) -> list[PushLine]:
        """The lines the blade runs to sweep this plate, left to right.

        Empty for a profile whose push-off does not follow the parts - the
        CoreXY machines still push through the plate centre in three fixed
        lanes.  The report and the G-code both read this, so neither can end up
        describing a push the other does not make.
        """
        return []

    def check_eject_clearance(self, print_body: str) -> None:
        """Refuse the build if the model fouls this printer's eject sequence.

        The default accepts anything, because pushing a part off with the
        gantry never brings the toolhead down onto the plate.  A profile whose
        eject sequence *does* descend onto the plate overrides this and raises
        :class:`~pylooprint.errors.UnsafeEjectZoneError`.
        """

    def build_machine_code(
        self,
        structure: GcodeStructure,
        context: EndCodeContext,
        values: Mapping[str, object],
    ) -> MachineCode:
        """Produce the start and end code that wrap one loop.

        This default throws the slicer's machine G-code away and substitutes
        this profile's templates, which is what the original web tool does.  It
        works for any printer but loses whatever the printer profile configured
        - flow calibration, bed levelling, build-plate detection.

        A profile that can instead *patch* the slicer's own machine G-code
        overrides this and uses ``structure.slicer_start_code`` /
        ``structure.slicer_end_code``; see :class:`~pylooprint.printers.a1_mini.A1MiniProfile`.
        """
        return MachineCode(
            start_code=render_start_code(self.start_code(), values),
            end_code=self.end_code(context),
            warnings=(f"{self.name} has no in-place machine G-code yet; using the Factorian templates",)
            + self.end_code_warnings(context),
        )
