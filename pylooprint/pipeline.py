"""The build pipeline: sliced project in, looped project out."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .core.constants import FALLBACK_MAX_Z_HEIGHT_MM, MAX_Z_HEIGHT_MM, MAX_Z_HEIGHT_RE, SIGNATURE
from .core.loop_builder import LoopPlan, build_looped_gcode
from .core.parking import read_slicer_park
from .core.parts import PartBounds, find_parts
from .core.placement import ExtrusionBounds, measure_extrusion_bounds
from .core.project import PROJECT_SETTINGS, SLICE_INFO, ThreeMfProject
from .core.push_plan import PushLine
from .core.structure import split_gcode
from .errors import AlreadyLoopedError, UnknownPrinterError
from .printers import EndCodeContext, PrinterProfile
from .printers.detection import detect_from_gcode_header, detect_from_model_id, detect_from_project_settings
from .settings import LoopSettings


@dataclass
class BuildResult:
    """The looped G-code plus what the pipeline learned along the way."""

    gcode: str
    profile: PrinterProfile
    max_layer_z: float
    max_layer_z_from_header: bool
    #: Box around everything printed; ``None`` when nothing extrudes.
    bounds: ExtrusionBounds | None = None
    #: One box per separate part on the plate, front-left first.
    parts: list[PartBounds] = field(default_factory=list)
    #: The push lines planned from those parts, left to right.  Empty for a
    #: profile whose push-off does not follow the parts.
    push_lines: list[PushLine] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def detect_printer(project: ThreeMfProject) -> PrinterProfile:
    """Identify the printer a project was sliced for."""
    profile = detect_from_model_id(project.text(SLICE_INFO))
    if profile is None:
        profile = detect_from_project_settings(project.text(PROJECT_SETTINGS))
    if profile is None:
        profile = detect_from_gcode_header(project.gcode)
    if profile is None:
        raise UnknownPrinterError(
            "could not detect the printer from the project; pass --printer explicitly"
        )
    return profile


def build_loops(
    project: ThreeMfProject,
    profile: PrinterProfile,
    settings: LoopSettings,
    *,
    source_name: str,
    generated_at: datetime | None = None,
) -> BuildResult:
    """Turn one sliced plate into an ``n``-times looped plate."""
    gcode = project.gcode
    warnings: list[str] = []

    if SIGNATURE in gcode:
        raise AlreadyLoopedError(f"{project.path.name} has already been looped")

    max_layer_z, from_header = _read_max_layer_z(gcode, warnings)
    structure = split_gcode(gcode)

    # Refuse before generating anything if the model sits where this printer
    # brings the toolhead down to eject the part.
    profile.check_eject_clearance(structure.print_body)

    # What is on the plate, part by part, and the push lines planned from it.
    # The end code is built from the same plan, so what is reported is what
    # the printer will run.  The press-and-swipe push measures where the blade
    # meets plastic, which only the G-code can say; the plain push works off
    # the boxes alone and is not charged for that scan.
    parts = find_parts(structure.print_body)
    push_lines = profile.push_plan(parts, structure.print_body if settings.zpush else "")

    blind = [
        number
        for number, line in enumerate(push_lines, start=1)
        if settings.zpush and line.contact_y is None
    ]
    if blind:
        warnings.append(
            "no plastic stands under the bumper at the push height on push "
            f"{'lines' if len(blind) > 1 else 'line'} "
            + ", ".join(str(number) for number in blind)
            + ": nothing there to work loose, so those lines push straight instead"
        )

    bounds = measure_extrusion_bounds(structure.print_body)
    context = EndCodeContext(
        settings=settings,
        parts=tuple(parts),
        push_lines=tuple(push_lines),
        # Where this plate would leave the head if it were printed once, the
        # ordinary way.  The last loop finishes there.
        slicer_park=read_slicer_park(structure.slicer_end_code),
        model_height=max_layer_z,
        centre_x=(bounds.min_x + bounds.max_x) / 2 if bounds else 0.0,
    )

    machine_code = profile.build_machine_code(structure, context)
    warnings.extend(machine_code.warnings)

    plan = LoopPlan(
        structure=structure,
        start_code=machine_code.start_code,
        end_code=machine_code.end_code,
        final_end_code=machine_code.final_end_code,
        loops=settings.loops,
        source_name=source_name,
        generated_at=generated_at,
    )

    return BuildResult(
        gcode=build_looped_gcode(plan),
        profile=profile,
        max_layer_z=max_layer_z,
        max_layer_z_from_header=from_header,
        bounds=bounds,
        parts=parts,
        push_lines=push_lines,
        warnings=warnings,
    )


def _read_max_layer_z(gcode: str, warnings: list[str]) -> tuple[float, bool]:
    """Model height, needed for every Z-drop decision in the end code."""
    match = MAX_Z_HEIGHT_RE.search(gcode)
    if match:
        try:
            value = float(match.group(1))
        except ValueError:
            value = 0.0
        if 0 < value <= MAX_Z_HEIGHT_MM:
            return value, True
    warnings.append(
        f"max_z_height not found in the G-code header; using {FALLBACK_MAX_Z_HEIGHT_MM:.0f}mm - "
        "check the generated push-off height before printing"
    )
    return FALLBACK_MAX_Z_HEIGHT_MM, False
