"""Shared engine for the CoreXY machines (P1/P1S and X1/X1C).

Kinematics: the bed is fixed and the gantry moves in X and Y, so the part is
pushed off by raising the bed and driving the toolhead forward along Y in three
lanes - one on the model centre and one either side of it for stability.

Nothing here may be reused by the bed-slinger profiles.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core.jsnum import number_to_string, to_fixed
from ..settings import (
    DEFAULT_PUSH_LANE_OFFSET,
    MAX_PUSH_LANE_OFFSET,
    MIN_PUSH_LANE_OFFSET,
    LoopSettings,
)
from .base import EndCodeContext, PrinterProfile, load_template

SWEEP_PASSES = 7
MIN_LANE_CLEARANCE = 10


@dataclass(frozen=True)
class PushLanes:
    """X positions the three push lanes and the safe parking move use."""

    safe_x: str
    left_x: str
    centre_x: str
    right_x: str
    adjusted_offset: float
    max_possible_offset: float
    #: Set when the requested lane offset had to be reduced to stay on the bed.
    warning: str | None = None


class CoreXyProfile(PrinterProfile):
    """Common behaviour of the X-axis multi-lane push printers."""

    start_template_flush: str
    start_template_no_flush: str

    def start_code(self, settings: LoopSettings) -> str:
        name = self.start_template_flush if settings.purge_enabled else self.start_template_no_flush
        return load_template(name)

    # -- push lanes --------------------------------------------------------
    def push_lanes(self, context: EndCodeContext) -> PushLanes:
        """Lane positions for the detected model, or the fixed fallback."""
        lanes = self.dynamic_push_lanes(context)
        return lanes if lanes is not None else self.fallback_push_lanes(context)

    def dynamic_push_lanes(self, context: EndCodeContext) -> PushLanes | None:
        min_x, max_x = context.model_min_x, context.model_max_x
        if not min_x or not max_x or min_x >= max_x:
            return None

        offset = context.settings.push_lane_offset
        if offset < MIN_PUSH_LANE_OFFSET or offset > MAX_PUSH_LANE_OFFSET:
            offset = DEFAULT_PUSH_LANE_OFFSET
        safe_offset = max(MIN_PUSH_LANE_OFFSET, min(MAX_PUSH_LANE_OFFSET, offset))

        bed = self.bed_bounds
        centre_x = (min_x + max_x) / 2
        bed_centre_x = (bed.min_x + bed.max_x) / 2
        max_possible = min(centre_x - bed.min_x, bed.max_x - centre_x)

        warning = None
        adjusted = safe_offset
        if safe_offset > max_possible:
            adjusted = max_possible
            warning = (
                f"Offset auto-adjusted from {to_fixed(safe_offset, 1)}mm to "
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
            adjusted_offset=adjusted,
            max_possible_offset=max_possible,
            warning=warning,
        )

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
            adjusted_offset=context.settings.validated_push_lane_offset,
            max_possible_offset=context.settings.validated_push_lane_offset,
        )

    def push_gcode(self, lanes: PushLanes, settings: LoopSettings) -> str:
        return (
            load_template("push_corexy.gcode")
            .replace("@X_START@", lanes.safe_x)
            .replace("@X_CENTER@", lanes.centre_x)
            .replace("@X_LEFT@", lanes.left_x)
            .replace("@X_RIGHT@", lanes.right_x)
            .replace("@PUSH_SPEED@", number_to_string(settings.validated_push_speed))
        )

    # -- optional full-bed sweep ------------------------------------------
    def sweep_gcode(self, settings: LoopSettings) -> str:
        """Seven back-to-front passes that clear anything left on the plate."""
        bed = self.bed_bounds
        speed = number_to_string(settings.validated_sweep_speed)
        z_low = to_fixed(settings.validated_sweep_z, 1)
        front_y = number_to_string(max(bed.min_y, 10))
        back_y = number_to_string(bed.max_y)
        spacing = (bed.max_x - bed.min_x) / (SWEEP_PASSES - 1)
        x_positions = [bed.min_x + index * spacing for index in range(SWEEP_PASSES)]

        code = (
            "; --- FULL BED SWEEP (Looprint) ---\n"
            "; SAFE one-way back-to-front pattern (7 passes across X-axis)\n"
            "; Pattern: Lift → Rapid return to back (in air) → Drop → Push forward slowly\n"
            f"; Speed: {speed}mm/min (forward push), F12000 (rapid return in air)\n"
            "M400 ; Wait for all motion to complete\n"
            "G1 E-0.5 F300 ; Retract filament slightly\n"
            f"G1 Z{z_low} F600 ; Move to bed level (as low as possible)\n"
            "M400 ; Wait for motion to complete\n"
            "\n"
            "; Start at back-left position\n"
            f"G1 X{to_fixed(x_positions[0], 1)} Y{back_y} F5000 ; Move to start position (left edge, back)\n"
        )

        for index, x_pos in enumerate(x_positions):
            x = to_fixed(x_pos, 1)
            code += (
                f"; --- PASS {index + 1}/{SWEEP_PASSES} (X={x}) ---\n"
                f"G1 X{x} Y{back_y} F{speed} ; Position at back\n"
                f"G1 X{x} Y{front_y} F{speed} ; PUSH: Forward from back to front (slow, clears debris)\n"
            )
            if index < SWEEP_PASSES - 1:
                code += (
                    f"G1 X{x} Y{back_y} F12000 ; RETURN: Move back to back edge in straight line (same X, fast)\n"
                    "M400 ; Wait for return to complete\n"
                    f"G1 X{to_fixed(x_positions[index + 1], 1)} Y{back_y} F12000 ; SHIFT: Move to next X position at back (fast)\n"
                    "M400 ; Wait for shift to complete\n"
                )

        code += (
            f"G1 X{number_to_string(bed.min_x)} Y{front_y} F12000 "
            "; Return to safe left position at front (avoids filament cutter)\n"
            "M400 ; Wait for all motion to complete\n"
            "; --- END FULL BED SWEEP ---\n"
        )
        return code
