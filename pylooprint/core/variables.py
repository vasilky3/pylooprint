"""Resolving the slicer variables a start/end template refers to.

Common to every printer.  Values come from the ``CONFIG_BLOCK`` first; when a
key is missing we fall back to the emitted G-code and finally to a safe default,
because a template that still contains ``[nozzle_temperature_initial_layer]``
would make the printer heat to nothing.
"""

from __future__ import annotations

import re
from typing import Mapping

from .config_block import config_list, config_value, parse_config_block
from .jsnum import to_fixed

#: Per-extruder settings the templates read with ``[initial_extruder]``.
_PER_EXTRUDER_KEYS = (
    "nozzle_temperature_initial_layer",
    "filament_type",
    "filament_max_volumetric_speed",
    "nozzle_temperature_range_high",
    "bed_temperature",
    "bed_temperature_initial_layer",
)

_SINGLE_KEYS = (
    "curr_bed_type",
    "hot_plate_temp_initial_layer",
    "cool_plate_temp_initial_layer",
    "bed_temperature_initial_layer_single",
)

_DEFAULTS = {
    "nozzle_temperature_initial_layer": "220",
    "bed_temperature_initial_layer_single": "60",
    "bed_temperature": "60",
    "bed_temperature_initial_layer": "60",
    "filament_max_volumetric_speed": "12",
    "nozzle_temperature_range_high": "240",
    "initial_extruder": "0",
}

_NOZZLE_TEMP_RE = re.compile(r"M104\s+S(\d+)\s*;.*nozzle.*temp", re.IGNORECASE)
_BED_TEMP_RE = re.compile(r"M140\s+S(\d+)", re.IGNORECASE)
_TOOL_RE = re.compile(r"T(\d+)")

BED_CENTRE_FALLBACK = "128"


def extract_variable_values(
    gcode: str,
    config_text: str,
    model_bounds: Mapping[str, float] | None = None,
) -> dict[str, object]:
    """Build the variable map used to render start and end templates.

    ``model_bounds`` is the optional ``minX/maxX/minY/maxY`` box from placement
    detection; it only matters when the slicer did not record
    ``first_layer_center_no_wipe_tower``.
    """
    config = parse_config_block(config_text)
    values: dict[str, object] = {"initial_extruder": config_value(config, "initial_extruder") or "0"}
    extruder = str(values["initial_extruder"])

    if config_text:
        for key in _PER_EXTRUDER_KEYS:
            values[key] = config_value(config, key, None, extruder)
        for key in _SINGLE_KEYS:
            values[key] = config_value(config, key)
        values["first_layer_center_no_wipe_tower"] = _first_layer_centre(config, extruder, model_bounds)
        _fill_bed_temperature_gaps(values)

    if not values.get("nozzle_temperature_initial_layer"):
        match = _NOZZLE_TEMP_RE.search(gcode)
        if match:
            values["nozzle_temperature_initial_layer"] = match.group(1)

    if not values.get("bed_temperature_initial_layer_single"):
        match = _BED_TEMP_RE.search(gcode)
        if match:
            values["bed_temperature_initial_layer_single"] = match.group(1)

    if values.get("initial_extruder") in (None, "", "0"):
        values["initial_extruder"] = _scan_initial_extruder(gcode)

    _fill_bed_temperature_gaps(values)

    for key, default in _DEFAULTS.items():
        if not values.get(key):
            values[key] = default

    if values.get("nozzle_temperature_range_high") in (None, "", "240"):
        nozzle = _to_int(values.get("nozzle_temperature_initial_layer"))
        if nozzle is not None:
            values["nozzle_temperature_range_high"] = str(nozzle + 20)

    return values


def _first_layer_centre(
    config: Mapping[str, object],
    extruder: str,
    model_bounds: Mapping[str, float] | None,
) -> list[str]:
    """The X/Y the push-off aligns to.  Two elements, always strings."""
    stored = config_list(config, "first_layer_center_no_wipe_tower")
    if stored is not None:
        return list(stored)

    first = config_value(config, "first_layer_center_no_wipe_tower", "0", extruder)
    second = config_value(config, "first_layer_center_no_wipe_tower", "1", extruder)
    if first or second:
        return [first or BED_CENTRE_FALLBACK, second or BED_CENTRE_FALLBACK]

    return [
        _centre_of(model_bounds, "minX", "maxX"),
        _centre_of(model_bounds, "minY", "maxY"),
    ]


def _centre_of(bounds: Mapping[str, float] | None, low_key: str, high_key: str) -> str:
    if not bounds or low_key not in bounds or high_key not in bounds:
        return BED_CENTRE_FALLBACK
    return to_fixed((float(bounds[low_key]) + float(bounds[high_key])) / 2, 2)


def _fill_bed_temperature_gaps(values: dict[str, object]) -> None:
    """Derive the bed temperatures the ``{if}`` conditionals compare against."""
    if not values.get("bed_temperature_initial_layer_single"):
        bed_type = str(values.get("curr_bed_type") or "").lower()
        if values.get("bed_temperature_initial_layer"):
            values["bed_temperature_initial_layer_single"] = values["bed_temperature_initial_layer"]
        elif values.get("bed_temperature"):
            values["bed_temperature_initial_layer_single"] = values["bed_temperature"]
        elif bed_type:
            hot = ("textured" in bed_type or "pei" in bed_type or "hot" in bed_type)
            if hot and values.get("hot_plate_temp_initial_layer"):
                values["bed_temperature_initial_layer_single"] = values["hot_plate_temp_initial_layer"]
            elif "cool" in bed_type and values.get("cool_plate_temp_initial_layer"):
                values["bed_temperature_initial_layer_single"] = values["cool_plate_temp_initial_layer"]

    single = values.get("bed_temperature_initial_layer_single")
    if single:
        if not values.get("bed_temperature"):
            values["bed_temperature"] = single
        if not values.get("bed_temperature_initial_layer"):
            values["bed_temperature_initial_layer"] = single


def _scan_initial_extruder(gcode: str) -> str:
    """Find the first real ``T`` command, ignoring ``T255``/``T1000``."""
    for match in _TOOL_RE.finditer(gcode):
        value = match.group(1)
        if value not in ("255", "1000"):
            return value
    return "0"


def _to_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None
