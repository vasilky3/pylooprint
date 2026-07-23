"""pylooprint - console tool that loops a sliced Bambu Lab plate.

A Python port of the Looprint web tool, split so that the G-code steps every
printer shares live in :mod:`pylooprint.core` and only the genuinely
machine-specific parts live in :mod:`pylooprint.printers`.
"""

__version__ = "0.1.0"
