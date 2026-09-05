"""Shared engine for the CoreXY machines (P1/P1S and X1/X1C).

Kinematics: the bed is fixed and the gantry moves in X and Y, so the part is
pushed off by raising the bed and driving the toolhead forward along Y in three
lanes - one on the model centre and one either side of it for stability.

Nothing here may be reused by the bed-slinger profiles.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.jsnum import number_to_string, to_fixed
from .base import EndCodeContext, PrinterProfile, load_template

#: Distance of the outer push lanes from the model centre.
PUSH_LANE_OFFSET = 30
#: Feedrate of the push move, in mm/min.
PUSH_SPEED = 300
MIN_LANE_CLEARANCE = 10


@dataclass(frozen=True)
class PushLanes:
    """X positions the three push lanes and the safe parking move use."""

    safe_x: str
    left_x: str
    centre_x: str
    right_x: str
    #: Set when the lane offset had to be reduced to stay on the bed.
    warning: str | None = None


class CoreXyProfile(PrinterProfile):
    """Common behaviour of the X-axis multi-lane push printers."""

    #: Declared for every machine, but nothing here reads them yet: these
    #: printers still push through the plate centre in three fixed lanes rather
    #: than following the parts.  See :func:`~pylooprint.core.push_plan`.
    blade_width = 55.0
    blade_overlap = 0.5

    # -- push lanes --------------------------------------------------------
    def push_lanes(self, context: EndCodeContext) -> PushLanes:
        """Lane positions for the detected model, or the fixed fallback."""
        lanes = self.dynamic_push_lanes(context)
        return lanes if lanes is not None else self.fallback_push_lanes(context)

    def dynamic_push_lanes(self, context: EndCodeContext) -> PushLanes | None:
        min_x, max_x = context.model_min_x, context.model_max_x
        if not min_x or not max_x or min_x >= max_x:
            return None

        bed = self.bed_bounds
        centre_x = (min_x + max_x) / 2
        bed_centre_x = (bed.min_x + bed.max_x) / 2
        max_possible = min(centre_x - bed.min_x, bed.max_x - centre_x)

        warning = None
        adjusted = PUSH_LANE_OFFSET
        if adjusted > max_possible:
            adjusted = max_possible
            warning = (
                f"Push lane offset auto-adjusted from {to_fixed(PUSH_LANE_OFFSET, 1)}mm to "
                f"{to_fixed(adjusted, 1)}mm to prevent collision. Maximum safe offset "
                f"for this model: {to_fixed(max_possible, 1)}mm."
            )

        left_x = max(bed.min_x, centre_x - adjusted)
        right_x = min(bed.max_x, centre_x + adjusted)
        safe_x = self._safe_parking_x(min_x, max_x, centre_x, bed_centre_x, 20)
        if any(abs(safe_x - lane) < MIN_LANE_CLEARANCE for lane in (left_x, centre_x, right_x)):
            safe_x = self._safe_parking_x(min_x, max_x, centre_x, bed_centre_x, 30)

        return PushLanes(
            safe_x=to_fixed(safe_x, 1),
            left_x=to_fixed(left_x, 1),
            centre_x=to_fixed(centre_x, 1),
            right_x=to_fixed(right_x, 1),
            warning=warning,
        )

    def end_code_warnings(self, context: EndCodeContext) -> tuple[str, ...]:
        warning = self.push_lanes(context).warning
        return (warning,) if warning else ()

    def _safe_parking_x(
        self, min_x: float, max_x: float, centre_x: float, bed_centre_x: float, clearance: float
    ) -> float:
        """Park away from the model so the retract move cannot clip it."""
        if centre_x < bed_centre_x:
            return max(self.bed_bounds.min_x, min_x - clearance)
        return min(self.bed_bounds.max_x, max_x + clearance)

    def fallback_push_lanes(self, context: EndCodeContext) -> PushLanes:
        """Fixed lanes used when the model could not be located."""
        bed_min_x = self.bed_bounds.min_x
        presets = {
            "center": (170, 108, 148, 148),
            "right": (220, 180, 220, 220),
            "left": (
                max(bed_min_x, 36),
                max(bed_min_x, 30),
                max(bed_min_x, 50),
                max(bed_min_x, 70),
            ),
        }
        safe_x, left_x, centre_x, right_x = presets.get(context.direction, presets["center"])
        return PushLanes(
            safe_x=number_to_string(safe_x),
            left_x=number_to_string(left_x),
            centre_x=number_to_string(centre_x),
            right_x=number_to_string(right_x),
        )

    def push_gcode(self, lanes: PushLanes) -> str:
        return (
            load_template("push_corexy.gcode")
            .replace("@X_START@", lanes.safe_x)
            .replace("@X_CENTER@", lanes.centre_x)
            .replace("@X_LEFT@", lanes.left_x)
            .replace("@X_RIGHT@", lanes.right_x)
            .replace("@PUSH_SPEED@", number_to_string(PUSH_SPEED))
        )
