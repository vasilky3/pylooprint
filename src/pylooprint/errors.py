"""Exceptions raised by pylooprint."""

from __future__ import annotations


class LooprintError(Exception):
    """Base class for every error the tool reports to the user."""


class UnsupportedFileError(LooprintError):
    """The input is not a 3MF container we know how to open."""


class GcodeNotFoundError(LooprintError):
    """No ``Metadata/plate_*.gcode`` inside the 3MF container."""


class AlreadyLoopedError(LooprintError):
    """The input already carries a Looprint signature."""


class UnknownPrinterError(LooprintError):
    """The printer model could not be detected and none was given."""
