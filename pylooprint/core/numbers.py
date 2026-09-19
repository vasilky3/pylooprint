"""Number formatting shared by the report and the G-code."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def to_fixed(value: float, digits: int) -> str:
    """``value`` with exactly ``digits`` decimals, halves rounded up.

    One formatter for both the console report and the emitted moves, so the
    operator reads the same figure the printer is given.
    """
    quantum = Decimal(1).scaleb(-digits)
    return str(Decimal(repr(float(value))).quantize(quantum, rounding=ROUND_HALF_UP))
