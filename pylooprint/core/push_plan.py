"""Which lines the blade has to run to sweep every part off the plate.

A bed slinger pushes by holding the toolhead still and driving the bed forward
under it, so one push sweeps a band of X: everything whose centre is under the
blade goes off the front.  A plate with one part needs one such line through its
centre - which is all the push-off used to do - but a plate with several needs
one line per part, or per group of parts standing on the same band.

Two numbers per machine decide the grouping: the width of the blade and how much
of it has to sit over a part to carry it.  Their product is the *reach* of a
line: a part is pushed by a line no further than ``reach`` from its centre.

The height is the other half of the plan.  A line pushes at a share of the model
height, and when it covers several parts that share is taken from the *shortest*
of them - the blade then touches every part of the group, and the taller ones are
simply struck lower down, which tips them over all the more readily.

Nothing here says how the blade *gets* to a line.  That order matters as much as
the positions do, and it belongs with the G-code: see
:meth:`~pylooprint.printers.bedslinger.BedSlingerProfile.push_gcode`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .parts import PartBounds


@dataclass(frozen=True)
class PushLine:
    """One pass of the blade: where it stands, and how high it rises there."""

    #: X the blade is centred on.
    x: float
    #: Z it rises to for the push, once it is standing on this line.
    z: float
    #: Y at which the blade first meets the parts on this line - their back edge,
    #: since the bed carries them towards the nozzle from there.
    contact_y: float
    #: Which parts this line pushes, numbered as the parts report numbers them.
    parts: tuple[int, ...]


def plan_push_lines(
    parts: Sequence[PartBounds],
    *,
    blade_width: float,
    overlap: float,
    height_factor: float,
    min_model_height: float,
    min_z: float,
) -> list[PushLine]:
    """The push lines for a plate, left to right.

    ``parts`` is the list the report numbers from 1; the order it arrives in is
    the order those numbers refer to, whatever order the lines come out in.
    """
    if not parts:
        return []

    reach = blade_width * overlap
    numbered = sorted(
        ((_centre(part), number, part) for number, part in enumerate(parts, start=1)),
        key=lambda entry: entry[0],
    )

    groups: list[list[tuple[float, int, PartBounds]]] = []
    for entry in numbered:
        # One line covers a group when it can sit within reach of every centre
        # in it, which is exactly the group spanning no more than two reaches.
        if groups and entry[0] - groups[-1][0][0] <= 2 * reach:
            groups[-1].append(entry)
        else:
            groups.append([entry])

    lines: list[PushLine] = []
    for group in groups:
        shortest = min(part.max_z for _, _, part in group)
        lines.append(
            PushLine(
                x=(group[0][0] + group[-1][0]) / 2,
                z=_push_height(shortest, height_factor, min_model_height, min_z),
                contact_y=max(part.max_y for _, _, part in group),
                parts=tuple(sorted(number for _, number, _ in group)),
            )
        )
    return lines


def _centre(part: PartBounds) -> float:
    return (part.min_x + part.max_x) / 2


def _push_height(top: float, factor: float, min_model_height: float, min_z: float) -> float:
    """Where the blade meets a part that tall - the rule the templates used."""
    return top * factor if top >= min_model_height else min_z
