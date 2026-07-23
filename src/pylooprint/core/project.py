"""Reading and rewriting a sliced 3MF project.

A ``.gcode.3mf`` is a plain zip; looping only ever rewrites
``Metadata/plate_N.gcode`` and copies every other member through untouched, so
thumbnails, model geometry and slicer settings survive.
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..errors import GcodeNotFoundError, UnsupportedFileError
from .constants import GCODE_IN_3MF_RE

SLICE_INFO = "Metadata/slice_info.config"
PROJECT_SETTINGS = "Metadata/project_settings.config"


@dataclass
class ThreeMfProject:
    """An opened 3MF container, held in memory."""

    path: Path
    members: dict[str, bytes]
    order: list[str]
    gcode_path: str

    @classmethod
    def open(cls, path: Path) -> "ThreeMfProject":
        if not zipfile.is_zipfile(path):
            raise UnsupportedFileError(f"{path.name} is not a 3MF container (expected a zip archive)")

        with zipfile.ZipFile(path) as archive:
            order = archive.namelist()
            members = {name: archive.read(name) for name in order}

        gcode_paths = [name for name in order if GCODE_IN_3MF_RE.match(name)]
        if not gcode_paths:
            raise GcodeNotFoundError(
                f"no G-code inside {path.name}; expected Metadata/plate_*.gcode - "
                "export the plate as '.gcode.3mf', not as a project file"
            )
        return cls(path=path, members=members, order=order, gcode_path=gcode_paths[0])

    @property
    def gcode(self) -> str:
        return self.members[self.gcode_path].decode("utf-8", errors="replace")

    def text(self, name: str) -> str:
        """Read a text member, returning ``''`` when it is absent."""
        data = self.members.get(name)
        return data.decode("utf-8", errors="replace") if data is not None else ""

    def save_as(self, destination: Path, gcode: str) -> None:
        """Write a copy of the project with ``gcode`` replacing the plate file."""
        payload = dict(self.members)
        payload[self.gcode_path] = gcode.encode("utf-8")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for name in self.order:
                archive.writestr(name, payload[name])
