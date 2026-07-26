"""Splitting a sliced plate G-code into the parts a loop is built from.

Common to every printer.  A Bambu/Orca plate file looks like this::

    ; HEADER_BLOCK_START ... ; HEADER_BLOCK_END
    ; CONFIG_BLOCK_START ... ; CONFIG_BLOCK_END
    ; EXECUTABLE_BLOCK_START
    <setup commands>
    ; FEATURE: Custom
    <machine start G-code>          <- replaced or patched by the profile
    ; CHANGE_LAYER ... <the print>  <- repeated once per loop
    ;===== date: ...                <- machine end G-code, replaced or patched
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .constants import (
    CONFIG_BLOCK_END,
    CONFIG_BLOCK_START,
    END_CODE_START_MARKER,
    EXECUTABLE_BLOCK_START,
    FEATURE_CUSTOM,
    LAYER_MARKER_RE,
)

_KEEP_COMMENT_RE = re.compile(r"; (CHANGE_LAYER|LAYER_CHANGE|layer num)", re.IGNORECASE)
_LEFTOVER_TEMP_RE = re.compile(r"^M(104|109)\s+S140", re.IGNORECASE)
_START_CODE_END_MARKER_RE = re.compile(r"; =+.*Start Code End.*=+", re.IGNORECASE)
_M109_RE = re.compile(r"M109\s+S\d+", re.IGNORECASE)
_FIRST_PRINT_AFTER_M109_RE = re.compile(r"(M73\s+P\d+|G1\s+X|G0\s+X|;LAYER|; layer)", re.IGNORECASE)
_FIRST_PRINT_RE = re.compile(r"(M73\s+P\d+|G1\s+X|G0\s+X|G28|;LAYER|; layer)", re.IGNORECASE)
_TOOL_RE = re.compile(r"T(\d+)")

#: Fragments that suggest the slicer start code survived the split.
_START_CODE_LEFTOVERS = ("G1 Z5 F300", "M17 X1.2 Y1.2 Z0.75", "G90\nM17 X1.2")


@dataclass(frozen=True)
class GcodeStructure:
    """The pieces a looped file is assembled from.

    ``header``, ``config``, ``setup`` and ``print_body`` are reused as-is by
    both strategies.  The two ``slicer_*`` fields hold the machine G-code that
    the Factorian strategy discards and the in-place strategy patches.
    """

    header: str
    config: str
    setup: str
    print_body: str
    original_tool_command: str | None
    #: Machine start G-code, between ``; FEATURE: Custom`` and the first layer.
    slicer_start_code: str = ""
    #: Machine end G-code, from the last ``;===== date:`` marker to the end.
    slicer_end_code: str = ""
    #: False when the file had no ``; EXECUTABLE_BLOCK_START`` to split on, in
    #: which case ``setup`` holds the whole file and must not be treated as a
    #: prologue that a start code can be appended to.
    recognised: bool = True


def split_gcode(plate_gcode: str) -> GcodeStructure:
    """Split a full plate G-code into the pieces a loop is built from."""
    end_index = plate_gcode.rfind(END_CODE_START_MARKER)
    if end_index == -1:
        gcode, slicer_end_code = plate_gcode, ""
    else:
        gcode, slicer_end_code = plate_gcode[:end_index].strip(), plate_gcode[end_index:]

    executable_start = gcode.find(EXECUTABLE_BLOCK_START)
    if executable_start == -1:
        return GcodeStructure(
            header="",
            config="",
            setup=gcode,
            print_body="",
            original_tool_command=None,
            slicer_end_code=slicer_end_code,
            recognised=False,
        )

    tool = extract_original_tool_command(gcode[executable_start:])

    header = gcode[:executable_start].strip()
    executable = gcode[executable_start:].strip()

    config = ""
    config_start = header.find(CONFIG_BLOCK_START)
    config_end = header.find(CONFIG_BLOCK_END)
    if config_start != -1 and config_end != -1:
        config = header[config_start : config_end + len(CONFIG_BLOCK_END)]
        header = header[:config_start].strip() + "\n" + header[config_end + len(CONFIG_BLOCK_END) :].strip()

    setup, slicer_start_code, print_body = _split_setup_and_print(executable)
    return GcodeStructure(
        header=header,
        config=config,
        setup=setup,
        print_body=print_body,
        original_tool_command=tool,
        slicer_start_code=slicer_start_code,
        slicer_end_code=slicer_end_code,
    )


def _split_setup_and_print(executable: str) -> tuple[str, str, str]:
    feature_index = executable.find(FEATURE_CUSTOM)
    if feature_index == -1:
        return executable, "", ""

    setup = executable[: feature_index + len(FEATURE_CUSTOM)]
    after_feature = executable[feature_index + len(FEATURE_CUSTOM) :]

    layer_marker = LAYER_MARKER_RE.search(after_feature)
    if layer_marker is None:
        return setup, "", _split_without_layer_marker(after_feature)

    slicer_start_code = after_feature[: layer_marker.start()].strip()
    print_body = _drop_leftover_start_code(after_feature[layer_marker.start() :])
    if any(fragment in print_body for fragment in _START_CODE_LEFTOVERS):
        leftover = _KEEP_COMMENT_RE.search(print_body)
        if leftover:
            print_body = print_body[leftover.start() :]
    return setup, slicer_start_code, print_body


def _split_without_layer_marker(after_feature: str) -> str:
    """Fallback used when the file has no layer-change comments at all."""
    m109_matches = list(_M109_RE.finditer(after_feature))
    if m109_matches:
        after_m109 = after_feature[m109_matches[-1].end() :]
        first_print = _FIRST_PRINT_AFTER_M109_RE.search(after_m109)
        return (after_m109[first_print.start() :] if first_print else after_m109).strip()

    first_print = _FIRST_PRINT_RE.search(after_feature)
    return (after_feature[first_print.start() :] if first_print else after_feature).strip()


def _drop_leftover_start_code(layer_start: str) -> str:
    """Skip comments and stale ``M104/M109 S140`` lines ahead of the print."""
    lines = layer_start.split("\n")
    offset = 0
    for line in lines[:20]:
        stripped = line.strip()
        if not stripped or (stripped.startswith(";") and not _KEEP_COMMENT_RE.search(stripped)):
            offset += len(line) + 1
            continue
        if _LEFTOVER_TEMP_RE.match(stripped):
            offset += len(line) + 1
            continue
        break
    return layer_start[offset:].strip()


def extract_original_tool_command(executable: str) -> str | None:
    """Recover the extruder index (``T0``..``T3``) used by the slicer start code.

    Without this the loop would inherit ``T255`` from the end code's unload
    sequence and the printer would refuse to extrude.
    """
    feature_index = executable.find(FEATURE_CUSTOM)
    if feature_index == -1:
        return None
    after_feature = executable[feature_index + len(FEATURE_CUSTOM) :]

    marker = _START_CODE_END_MARKER_RE.search(after_feature)
    if marker:
        start_code = after_feature[: marker.start()]
    else:
        layer_marker = LAYER_MARKER_RE.search(after_feature)
        start_code = after_feature[: layer_marker.start()] if layer_marker else after_feature[:5000]

    for match in _TOOL_RE.finditer(start_code):
        if 0 <= int(match.group(1)) < 4:
            return match.group(1)
    return None
