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
from typing import Mapping

from ..core.placement import ExtrusionBounds
from ..core.structure import GcodeStructure
from ..core.template import render_start_code
from ..settings import LoopSettings

_TEMPLATE_PACKAGE = "pylooprint.printers.templates"


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

    def apply_temp_offset(self, temp: int) -> int:
        """Bed temperature to actually command for a requested cool-down temp."""
        return temp

    def cooldown_block(self, temp: int) -> str:
        """The repeated ``M190`` wait that holds the print until it releases."""
        return "\n".join([f"M190 S{self.apply_temp_offset(temp)}"] * self.m190_repeat)

    @abstractmethod
    def start_code(self, settings: LoopSettings) -> str:
        """Raw start-code template, before variable substitution."""

    @abstractmethod
    def end_code(self, context: EndCodeContext) -> str:
        """Cool-down and push-off sequence appended after every loop."""

    def check_eject_clearance(self, bounds: ExtrusionBounds | None) -> None:
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
        speed_mode = context.settings.speed_mode
        return MachineCode(
            start_code=render_start_code(self.start_code(context.settings), values, speed_mode),
            end_code=self.end_code(context),
            warnings=(f"{self.name} has no in-place machine G-code yet; using the Factorian templates",),
        )
