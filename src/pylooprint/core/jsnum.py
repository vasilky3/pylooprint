"""Number formatting that matches JavaScript.

The reference implementation is JavaScript, and its output is compared
byte-for-byte in the tests, so ``Number.prototype.toFixed`` (round-half-away-
from-zero on the decimal expansion of the double) has to be reproduced rather
than Python's round-half-to-even ``format``.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal


def to_fixed(value: float, digits: int) -> str:
    """Return ``value`` formatted like JavaScript's ``toFixed(digits)``."""
    quantum = Decimal(1).scaleb(-digits)
    return str(Decimal(repr(float(value))).quantize(quantum, rounding=ROUND_HALF_UP))


def number_to_string(value: float) -> str:
    """Return ``value`` formatted like JavaScript's ``String(number)``."""
    if value != value or value in (float("inf"), float("-inf")):  # pragma: no cover
        return repr(value)
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))
