"""Working out which printer a sliced project was made for.

Three sources are tried in order of reliability: the plate metadata, the saved
project settings and finally the G-code header.  X1 is always tested before P1
because ``X1`` matches a bare ``P1`` search in some profile names.
"""

from __future__ import annotations

import re

from . import PrinterProfile, get_profile

_MODEL_ID_RE = (
    re.compile(r"""key=["']printer_model_id["'][^>]*value=["']([^"']+)["']""", re.IGNORECASE),
    re.compile(r"""printer_model_id[^>]*value=["']([^"']+)["']""", re.IGNORECASE),
)
_VALUE_RE = re.compile(r"""value=["']([^"']+)["']""", re.IGNORECASE)


def detect_from_model_id(slice_info: str) -> PrinterProfile | None:
    """Read ``printer_model_id`` out of ``Metadata/slice_info.config``."""
    model_id = _read_model_id(slice_info)
    if not model_id:
        return None
    model_id = model_id.upper().strip()

    if model_id in ("BL-P001", "BL-P002", "C12", "X1", "X1C") or (
        "X1" in model_id and "P1" not in model_id
    ):
        return get_profile("x1")
    if model_id == "N1" or "A1MINI" in model_id or "A1 MINI" in model_id:
        return get_profile("a1mini")
    if model_id == "N2S" or "A1" in model_id:
        return get_profile("a1")
    if model_id == "C11" or "P1" in model_id:
        return get_profile("p1")
    return None


def detect_from_project_settings(project_settings: str) -> PrinterProfile | None:
    """Fall back to the printer preset names in ``project_settings.config``."""
    if "@BBL X1C" in project_settings or "@BBL X1" in project_settings:
        return get_profile("x1")
    if "@BBL A1 Mini" in project_settings:
        return get_profile("a1mini")
    if "@BBL A1" in project_settings:
        return get_profile("a1")
    if any(marker in project_settings for marker in ("@BBL P1P", "@BBL P1S", "@BBL P1")):
        return get_profile("p1")
    return None


def detect_from_gcode_header(gcode: str) -> PrinterProfile | None:
    """Last resort: the ``;===== machine:`` banner the slicer emits."""
    header = "\n".join(gcode.split("\n")[:100])
    if ";===== machine: X1" in header or "@BBL X1C" in header or "@BBL X1" in header:
        return get_profile("x1")
    if "A1 mini" in header or "A1Mini" in header:
        return get_profile("a1mini")
    if re.search(r";=====\s*machine:\s*A1", header, re.IGNORECASE):
        return get_profile("a1")
    if "P1" in header:
        return get_profile("p1")
    return None


def _read_model_id(slice_info: str) -> str | None:
    for pattern in _MODEL_ID_RE:
        match = pattern.search(slice_info)
        if match:
            return match.group(1)
    for line in slice_info.split("\n"):
        if "printer_model_id" in line:
            match = _VALUE_RE.search(line)
            if match:
                return match.group(1)
    return None
