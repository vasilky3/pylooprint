"""Editing the slicer's own G-code in place.

The default strategy replaces the machine start and end code wholesale with
Factorian's templates.  The in-place strategy instead keeps what the slicer
emitted and rewrites just the parts that are wrong for a looping print - the
purge lines that would be drawn onto an occupied plate, and the tail of the end
code where the part has to be cooled and ejected.

Both edits are anchored on text the slicer emits verbatim, and both raise
:class:`PatchError` when an anchor is missing rather than silently producing
G-code that does something else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Sequence

from ..errors import LooprintError


class PatchError(LooprintError):
    """An anchor a patch depends on was not found."""


@dataclass(frozen=True)
class LineRangePatch:
    """Replace a run of lines, keeping the indentation of the first one.

    Searching begins after the line matching :attr:`after`, which scopes the
    patch to one block - the same move can occur in several places in a plate
    file.  The run then starts at the first line matching :attr:`first`, ends at
    the next line matching :attr:`last`, and extends by :attr:`extra_lines`
    further lines.  Patterns are matched against the stripped line, so a patch
    does not have to know how deeply the slicer indented the block.
    """

    name: str
    first: str
    last: str
    replacement: tuple[str, ...]
    extra_lines: int = 0
    after: str | None = None

    def apply(self, gcode: str) -> str:
        first_re, last_re = re.compile(self.first), re.compile(self.last)
        lines = gcode.split("\n")

        begin = 0
        if self.after is not None:
            scope = _find(lines, re.compile(self.after), 0)
            if scope is None:
                raise PatchError(f"patch {self.name!r}: no line matching {self.after!r}")
            begin = scope + 1

        start = _find(lines, first_re, begin)
        if start is None:
            raise PatchError(f"patch {self.name!r}: no line matching {self.first!r}")
        end = _find(lines, last_re, start)
        if end is None:
            raise PatchError(f"patch {self.name!r}: no line matching {self.last!r} after line {start + 1}")
        end += self.extra_lines
        if end >= len(lines):
            raise PatchError(f"patch {self.name!r}: run extends past the end of the file")

        indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
        patched = [indent + line if line else line for line in self.replacement]
        return "\n".join(lines[:start] + patched + lines[end + 1 :])


def apply_patches(gcode: str, patches: Sequence[LineRangePatch]) -> str:
    """Apply patches in order; each one searches what the previous ones left."""
    for patch in patches:
        gcode = patch.apply(gcode)
    return gcode


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


def _find(lines: list[str], pattern: re.Pattern[str], begin: int) -> int | None:
    for index in range(begin, len(lines)):
        if pattern.match(lines[index].strip()):
            return index
    return None
