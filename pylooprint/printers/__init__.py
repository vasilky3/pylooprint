"""Printer profile registry.

Adding a machine means a package here and one entry in ``_PROFILES``; nothing in
:mod:`pylooprint.core` needs to change.
"""

from __future__ import annotations

from .a1 import A1Profile
from .a1mini import A1MiniProfile
from .base import BedBounds, EndCodeContext, MachineCode, PrinterProfile

_PROFILES: dict[str, PrinterProfile] = {
    profile.key: profile for profile in (A1MiniProfile(), A1Profile())
}

__all__ = [
    "A1MiniProfile",
    "A1Profile",
    "BedBounds",
    "EndCodeContext",
    "MachineCode",
    "PrinterProfile",
    "available_profiles",
    "get_profile",
]


def get_profile(key: str) -> PrinterProfile:
    """Look a profile up by its CLI key (``a1mini``, ``a1``)."""
    try:
        return _PROFILES[key.lower()]
    except KeyError:
        raise KeyError(f"unknown printer '{key}'; choose one of {', '.join(_PROFILES)}") from None


def available_profiles() -> dict[str, PrinterProfile]:
    return dict(_PROFILES)
