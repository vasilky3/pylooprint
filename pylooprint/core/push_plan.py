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

from dataclasses import dataclass, replace
from typing import Sequence

from .parts import PartBounds
from .placement import ExtrusionSegment, iter_extrusion_segments


@dataclass(frozen=True)
class PushLine:
    """One pass of the blade: where it stands, and how high it rises there."""

    #: X the blade is centred on.
    x: float
    #: Z it rises to for the push, once it is standing on this line.
    z: float
    #: Y at which the blade first meets plastic on this line.  Planned from the
    #: parts' back edges - the bed carries them towards the nozzle from there -
    #: and re-measured off the G-code by :func:`measure_contact` when it matters.
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


def measure_contact(
    print_body: str, lines: Sequence[PushLine], *, reach: float
) -> list[PushLine]:
    """Re-read each line's contact Y off the G-code, under the bumper.

    A part's hitbox answers a different question: it is the back edge of the whole
    footprint, over the whole height.  What the blade meets is the back edge of
    whatever stands *inside the width of the bumper* and *at or above the height
    the blade is at* - which on a cone is far closer to the centre than the
    footprint suggests, and on a crowded plate can belong to a neighbouring part
    rather than to the one this line is aimed at.  Either way it is the plastic the
    blade runs into, so it is where the approach has to stop.

    ``reach`` is the same ``blade_width * overlap`` the grouping uses, so the band
    that decides a contact and the band that decides a group cannot disagree.

    Every line keeps its planned value if nothing is found inside its band.
    """
    if not lines:
        return []

    bands = [(line.x - reach, line.x + reach, line.z) for line in lines]
    found: list[float | None] = [None] * len(lines)

    for segment in iter_extrusion_segments(print_body):
        for index, (low_x, high_x, push_z) in enumerate(bands):
            # Anything lower than the blade passes underneath it; that is what the
            # push height is for.
            if segment.z < push_z:
                continue
            y = _max_y_inside(segment, low_x, high_x)
            if y is not None and (found[index] is None or y > found[index]):
                found[index] = y

    return [
        line if contact is None else replace(line, contact_y=contact)
        for line, contact in zip(lines, found)
    ]


def _max_y_inside(segment: ExtrusionSegment, low_x: float, high_x: float) -> float | None:
    """The furthest Y the part of this move inside the X band reaches.

    Clipped rather than judged by its endpoints: a long diagonal can end well
    outside the bumper, and its far end says nothing about what is under it.
    """
    span = segment.x1 - segment.x0
    if span == 0:
        return max(segment.y0, segment.y1) if low_x <= segment.x0 <= high_x else None

    edges = sorted(((low_x - segment.x0) / span, (high_x - segment.x0) / span))
    enter, leave = max(edges[0], 0.0), min(edges[1], 1.0)
    if enter > leave:
        return None

    rise = segment.y1 - segment.y0
    return max(segment.y0 + rise * enter, segment.y0 + rise * leave)


def _centre(part: PartBounds) -> float:
    return (part.min_x + part.max_x) / 2


def _push_height(top: float, factor: float, min_model_height: float, min_z: float) -> float:
    """Where the blade meets a part that tall - the rule the templates used."""
    return top * factor if top >= min_model_height else min_z
