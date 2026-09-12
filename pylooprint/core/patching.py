"""Editing the slicer's own G-code in place.

The default strategy replaces the machine start and end code wholesale with
Factorian's templates.  The in-place strategy instead keeps what the slicer
emitted and rewrites just the one part that is wrong for a looping print: the
tail of the end code, where the part has to be cooled and ejected.  (The start
code is left alone - the purge that looping needs is the looping profile's job,
see ``profiles/source/a1mini_start.gcode``.)

The edit is anchored on text the slicer emits verbatim, and raises
:class:`PatchError` when an anchor is missing rather than silently producing
G-code that does something else.
"""

from __future__ import annotations

from typing import Callable

from ..errors import LooprintError


class PatchError(LooprintError):
    """An anchor a patch depends on was not found."""


def replace_between(gcode: str, after: str, before: str, build: Callable[[str], str]) -> str:
    """Rewrite the text between two unique anchor lines.

    ``build`` receives the text being replaced, so it can carry parts of it
    over - the end-code splice reuses the slicer's own Z-lift moves that way.
    """
    start = gcode.find(after)
    if start == -1:
        raise PatchError(f"anchor not found: {after!r}")
    start += len(after)
    end = gcode.find(before, start)
    if end == -1:
        raise PatchError(f"anchor not found after {after!r}: {before!r}")
    return gcode[:start] + build(gcode[start:end]) + gcode[end:]
