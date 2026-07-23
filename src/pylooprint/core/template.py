"""The slicer-template engine.

Bambu/Orca start and end G-code templates use three notations:

* ``[name]``            - plain substitution
* ``{expression}``      - arithmetic, e.g. ``{max_layer_z - 40}``
* ``{if cond}...{endif}`` - conditional blocks

Only the handful of forms that actually occur in the shipped templates are
implemented; anything unknown is deliberately left untouched so the printer's
own firmware sees exactly what the original tool emitted.
"""

from __future__ import annotations

import re
from typing import Mapping

from .jsnum import number_to_string, to_fixed

# --- conditionals ----------------------------------------------------------
_BED_TEMP_IF_RE = re.compile(
    r"\{if\s+\(bed_temperature\[initial_extruder\]\s*>\s*45\)\|\|"
    r"\(bed_temperature_initial_layer\[initial_extruder\]\s*>\s*45\)\}(.*?)\{endif\}",
    re.IGNORECASE | re.DOTALL,
)
_PLA_IF_RE = re.compile(
    r'\{if\s+filament_type\[initial_extruder\]=="PLA"\}(.*?)\{endif\}',
    re.IGNORECASE | re.DOTALL,
)
_BED_TYPE_IF_RE = re.compile(
    r'\{if\s+curr_bed_type=="Textured PEI Plate"\}(.*?)\{endif\}',
    re.IGNORECASE | re.DOTALL,
)

# --- expressions -----------------------------------------------------------
_NO_SUPPORT_IN_EXPR_RE = re.compile(r"\{([^}]*)\[initial_no_support_extruder\]([^}]*)\}")
_OUTER_WALL_RE = re.compile(r"\{outer_wall_volumetric_speed[^}]*\}")
_M220_WITH_COMMENT_RE = re.compile(r"M220\s+S100\s*;.*Reset\s+Feedrate", re.IGNORECASE)
_M220_BARE_RE = re.compile(r"M220\s+S100\s*$", re.MULTILINE)

# --- max_layer_z -----------------------------------------------------------
_MAX_Z_IF_RE = re.compile(
    r"\{if\s*\(?\s*max_layer_z\s*\)?\s*>\s*([\d.]+)\}(.*?)\{else\}(.*?)\{endif\}",
    re.DOTALL,
)
_MAX_Z_PLAIN_RE = re.compile(r"\{max_layer_z\}")
_MAX_Z_MATH_RE = re.compile(r"\{max_layer_z\s*([+\-])\s*([\d.]+)\}")

VOLUMETRIC_DIVISOR = 2.4053
VOLUMETRIC_FALLBACK = "1200"


def render_start_code(template: str, values: Mapping[str, object], speed_mode: int) -> str:
    """Fill a printer start-code template with values from the sliced file."""
    result = template
    result = _apply_conditionals(result, values)
    result = _apply_expressions(result, values)
    result = _apply_brackets(result, values)
    result = _apply_speed_mode(result, speed_mode)
    result = _apply_trailing_expressions(result, values)
    return result


# --------------------------------------------------------------------------
# conditionals
# --------------------------------------------------------------------------
def _apply_conditionals(text: str, values: Mapping[str, object]) -> str:
    bed_temp = _first_present(values, "bed_temperature", "bed_temperature_initial_layer_single")
    bed_temp_initial = _first_present(
        values, "bed_temperature_initial_layer", "bed_temperature_initial_layer_single"
    )
    for key in ("hot_plate_temp_initial_layer", "cool_plate_temp_initial_layer"):
        plate = _as_float(values.get(key), None)
        if plate is None:
            continue
        if bed_temp == 0:
            bed_temp = plate
        if bed_temp_initial == 0:
            bed_temp_initial = plate

    hot_bed = bed_temp > 45 or bed_temp_initial > 45
    text = _BED_TEMP_IF_RE.sub(lambda m: m.group(1).strip() if hot_bed else "", text)

    is_pla = str(values.get("filament_type") or "").upper() == "PLA"
    text = _PLA_IF_RE.sub(lambda m: m.group(1) if is_pla else "", text)

    textured = "Textured PEI" in str(values.get("curr_bed_type") or "")
    text = _BED_TYPE_IF_RE.sub(lambda m: m.group(1) if textured else "", text)
    return text


# --------------------------------------------------------------------------
# {expressions}
# --------------------------------------------------------------------------
def _apply_expressions(text: str, values: Mapping[str, object]) -> str:
    extruder = _effective_extruder(values)

    # Resolve the index inside expressions first, so that a later blanket
    # replacement cannot turn `speed[initial_no_support_extruder]/x` into
    # `speed0/x`.
    text = _NO_SUPPORT_IN_EXPR_RE.sub(lambda m: "{%s[%s]%s}" % (m.group(1), extruder, m.group(2)), text)

    nozzle = _as_float(values.get("nozzle_temperature_initial_layer"), 220.0)
    text = _replace_nozzle_expressions(text, nozzle)

    volumetric = _volumetric_feedrate(values)
    for pattern in (
        r"\{filament_max_volumetric_speed\[initial_extruder\]/2\.4053\*60\}",
        r"\{filament_max_volumetric_speed\[\d+\]/2\.4053\*60\}",
        r"\{filament_max_volumetric_speed/2\.4053\*60\}",
    ):
        text = re.sub(pattern, volumetric, text)

    text = text.replace("[initial_no_support_extruder]", extruder)
    text = _OUTER_WALL_RE.sub(VOLUMETRIC_FALLBACK, text)

    range_high = _range_high(values)
    text = re.sub(r"\{nozzle_temperature_range_high\[initial_extruder\]\}", range_high, text)
    text = re.sub(r"\{nozzle_temperature_range_high\[\d+\]\}", range_high, text)

    return text.replace("{+0.0}", "0.0")


def _replace_nozzle_expressions(text: str, nozzle: float) -> str:
    minus20 = number_to_string(nozzle - 20)
    plain = number_to_string(nozzle)
    text = re.sub(r"\{nozzle_temperature_initial_layer\[initial_extruder\]-20\}", minus20, text)
    text = re.sub(r"\{nozzle_temperature_initial_layer\[\d+\]-20\}", minus20, text)
    text = re.sub(r"\{nozzle_temperature_initial_layer\[initial_extruder\]\}", plain, text)
    return re.sub(r"\{nozzle_temperature_initial_layer\[\d+\]\}", plain, text)


# --------------------------------------------------------------------------
# [brackets]
# --------------------------------------------------------------------------
def _apply_brackets(text: str, values: Mapping[str, object]) -> str:
    nozzle = str(values.get("nozzle_temperature_initial_layer") or "220")
    text = text.replace("[nozzle_temperature_initial_layer]", nozzle)

    centre = values.get("first_layer_center_no_wipe_tower")
    centre_x, centre_y = centre_coordinates(centre)
    text = substitute_first_layer_centre(text, centre_x, centre_y)

    bed = str(values.get("bed_temperature_initial_layer_single") or "60")
    text = text.replace("[bed_temperature_initial_layer_single]", bed)

    extruder = _effective_extruder(values)
    text = text.replace("[initial_extruder]", extruder)
    return text.replace("[initial_no_support_extruder]", extruder)


def _apply_speed_mode(text: str, speed_mode: int) -> str:
    replacement = f"M220 S{speed_mode} ;Reset Feedrate (Looprint: {speed_mode}% speed)"
    text = _M220_WITH_COMMENT_RE.sub(replacement, text)
    return _M220_BARE_RE.sub(replacement, text)


def _apply_trailing_expressions(text: str, values: Mapping[str, object]) -> str:
    """Second pass for the A1 templates, which repeat some expression forms."""
    nozzle = _as_float(values.get("nozzle_temperature_initial_layer"), 220.0)
    text = re.sub(
        r"\{nozzle_temperature_initial_layer\[initial_no_support_extruder\]\}",
        number_to_string(nozzle),
        text,
    )
    for delta in (20, 50):
        text = re.sub(
            r"\{nozzle_temperature_initial_layer\[initial_no_support_extruder\]-%d\}" % delta,
            number_to_string(nozzle - delta),
            text,
        )
    text = re.sub(r"\{nozzle_temperature_initial_layer\[\d+\]\}", number_to_string(nozzle), text)
    for delta in (20, 50):
        text = re.sub(
            r"\{nozzle_temperature_initial_layer\[\d+\]-%d\}" % delta,
            number_to_string(nozzle - delta),
            text,
        )

    range_high = _range_high(values)
    text = re.sub(r"\{nozzle_temperature_range_high\[initial_no_support_extruder\]\}", range_high, text)
    text = re.sub(r"\{nozzle_temperature_range_high\[\d+\]\}", range_high, text)

    filament_type = values.get("filament_type")
    if filament_type:
        text = re.sub(r"\{filament_type\[initial_no_support_extruder\]\}", str(filament_type), text)
        text = re.sub(r"\{filament_type\[\d+\]\}", str(filament_type), text)

    if values.get("filament_max_volumetric_speed"):
        volumetric = _volumetric_feedrate(values)
        text = re.sub(
            r"\{filament_max_volumetric_speed\[initial_no_support_extruder\]/2\.4053\*60\}",
            volumetric,
            text,
        )
        text = re.sub(r"\{filament_max_volumetric_speed\[\d+\]/2\.4053\*60\}", volumetric, text)
    return text


# --------------------------------------------------------------------------
# max_layer_z / model centre - used by the end codes
# --------------------------------------------------------------------------
def resolve_max_layer_z(text: str, max_layer_z: float, *, from_header: bool = True) -> str:
    """Evaluate the Z-drop conditional and every ``{max_layer_z ...}`` term.

    ``from_header`` mirrors the original ordering: when the height came from the
    file header the conditional is evaluated first, when it is the 50 mm
    fallback the plain substitutions run first.
    """
    if from_header:
        text = _MAX_Z_IF_RE.sub(lambda m: _pick_z_branch(m, max_layer_z, trim_if=True), text)
        return _substitute_max_layer_z(text, max_layer_z)
    text = _substitute_max_layer_z(text, max_layer_z)
    return _MAX_Z_IF_RE.sub(lambda m: _pick_z_branch(m, max_layer_z, trim_if=False), text)


def _pick_z_branch(match: re.Match[str], max_layer_z: float, *, trim_if: bool) -> str:
    try:
        threshold = float(match.group(1))
    except ValueError:  # pragma: no cover - guarded by the regex
        return match.group(0)
    if max_layer_z > threshold:
        branch = _substitute_max_layer_z(match.group(2), max_layer_z)
        return branch.strip() if trim_if else branch
    return _substitute_max_layer_z(match.group(3), max_layer_z)


def _substitute_max_layer_z(text: str, max_layer_z: float) -> str:
    text = _MAX_Z_PLAIN_RE.sub(to_fixed(max_layer_z, 2), text)

    def arithmetic(match: re.Match[str]) -> str:
        value = float(match.group(2))
        total = max_layer_z + value if match.group(1) == "+" else max_layer_z - value
        return to_fixed(total, 2)

    return _MAX_Z_MATH_RE.sub(arithmetic, text)


def substitute_first_layer_centre(text: str, centre_x: str, centre_y: str) -> str:
    """Replace the model-centre placeholders used by the push-off moves."""
    text = text.replace("{first_layer_center_no_wipe_tower[0]}", centre_x)
    return text.replace("{first_layer_center_no_wipe_tower[1]}", centre_y)


def centre_coordinates(centre: object, fallback: tuple[str, str] = ("128", "128")) -> tuple[str, str]:
    """Normalise the ``first_layer_center_no_wipe_tower`` pair into two strings."""
    if isinstance(centre, (list, tuple)) and len(centre) >= 2:
        return (str(centre[0]) or fallback[0], str(centre[1]) or fallback[1])
    return fallback


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _effective_extruder(values: Mapping[str, object]) -> str:
    return str(values.get("originalToolCommand") or values.get("initial_extruder") or "0")


def _volumetric_feedrate(values: Mapping[str, object]) -> str:
    speed = _as_float(values.get("filament_max_volumetric_speed"), None)
    if speed is None:
        return VOLUMETRIC_FALLBACK
    return str(_js_round(speed / VOLUMETRIC_DIVISOR * 60))


def _range_high(values: Mapping[str, object]) -> str:
    stored = values.get("nozzle_temperature_range_high")
    if stored:
        return str(stored)
    nozzle = _as_float(values.get("nozzle_temperature_initial_layer"), None)
    return str(int(nozzle) + 20) if nozzle is not None else "240"


def _first_present(values: Mapping[str, object], *keys: str) -> float:
    """First key that carries any value at all, parsed as a number."""
    for key in keys:
        value = values.get(key)
        if value:
            return _as_float(value, 0.0) or 0.0
    return 0.0


def _as_float(value: object, default: float | None = 0.0) -> float | None:
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return default


def _js_round(value: float) -> int:
    """``Math.round``: halves go towards +infinity, unlike Python's ``round``."""
    import math

    return math.floor(value + 0.5)
