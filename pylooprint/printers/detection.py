"""Working out which printer a sliced project was made for.

Three sources are tried in order of reliability: the plate metadata, the saved
project settings and finally the G-code header.  The A1 Mini is always tested
before the A1, whose name is a prefix of it.
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

    if model_id == "N1" or "A1MINI" in model_id or "A1 MINI" in model_id:
        return get_profile("a1mini")
    if model_id == "N2S" or "A1" in model_id:
        return get_profile("a1")
    return None


def detect_from_project_settings(project_settings: str) -> PrinterProfile | None:
    """Fall back to the printer preset names in ``project_settings.config``."""
    if "@BBL A1 Mini" in project_settings or "@BBL A1M" in project_settings:
        return get_profile("a1mini")
    if "@BBL A1" in project_settings:
        return get_profile("a1")
    return None


def detect_from_gcode_header(gcode: str) -> PrinterProfile | None:
    """Last resort: the ``;===== machine:`` banner the slicer emits."""
    header = "\n".join(gcode.split("\n")[:100])
    if "A1 mini" in header or "A1Mini" in header:
        return get_profile("a1mini")
    if re.search(r";=====\s*machine:\s*A1", header, re.IGNORECASE):
        return get_profile("a1")
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
