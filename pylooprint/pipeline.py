"""The build pipeline: sliced project in, looped project out.

The order of the steps here is the contract between the common code and the
printer profiles, and it is the same order the original web tool used.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .core.constants import FALLBACK_MAX_Z_HEIGHT_MM, LOOPRINT_WATERMARKS, MAX_Z_HEIGHT_MM, MAX_Z_HEIGHT_RE
from .core.loop_builder import LoopPlan, build_looped_gcode
from .core.placement import ModelPlacement, determine_model_placement, measure_extrusion_bounds
from .core.project import PROJECT_SETTINGS, SLICE_INFO, ThreeMfProject
from .core.structure import split_gcode
from .core.template import centre_coordinates, resolve_max_layer_z, substitute_first_layer_centre
from .core.variables import extract_variable_values
from .errors import AlreadyLoopedError, UnknownPrinterError
from .printers import EndCodeContext, PrinterProfile
from .printers.detection import detect_from_gcode_header, detect_from_model_id, detect_from_project_settings
from .settings import LoopSettings


@dataclass
class BuildResult:
    """The looped G-code plus what the pipeline learned along the way."""

    gcode: str
    profile: PrinterProfile
    placement: ModelPlacement
    max_layer_z: float
    max_layer_z_from_header: bool
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
    force: bool = False,
) -> BuildResult:
    """Turn one sliced plate into an ``n``-times looped plate."""
    gcode = project.gcode
    warnings: list[str] = []

    watermark = next((mark for mark in LOOPRINT_WATERMARKS if mark in gcode), None)
    if watermark:
        message = f"{project.path.name} has already been looped (found {watermark!r})"
        if not force:
            raise AlreadyLoopedError(message + "; pass --force to loop it anyway")
        warnings.append(message)

    max_layer_z, from_header = _read_max_layer_z(gcode, warnings)
    structure = split_gcode(gcode)

    # Refuse before generating anything if the model sits where this printer
    # brings the toolhead down to eject the part.
    profile.check_eject_clearance(measure_extrusion_bounds(structure.print_body))

    bed = profile.bed_bounds
    placement = determine_model_placement(gcode, bed.min_x, bed.max_x, bed.min_y, bed.max_y)
    values = extract_variable_values(gcode, structure.config, placement.as_bounds())
    values["originalToolCommand"] = structure.original_tool_command

    context = EndCodeContext(
        settings=settings,
        model_min_x=placement.min_x,
        model_max_x=placement.max_x,
        direction=placement.direction,
    )

    # How the machine G-code is produced - patched in place, or replaced with
    # the profile's templates - is the profile's own decision.
    machine_code = profile.build_machine_code(structure, context, values)
    warnings.extend(machine_code.warnings)

    centre_x, centre_y = centre_coordinates(values.get("first_layer_center_no_wipe_tower"))
    end_code = substitute_first_layer_centre(machine_code.end_code, centre_x, centre_y)
    end_code = resolve_max_layer_z(end_code, max_layer_z, from_header=from_header)

    plan = LoopPlan(
        structure=structure,
        start_code=machine_code.start_code,
        end_code=end_code,
        loops=settings.loops,
        speed_mode=settings.speed_mode,
        source_name=source_name,
        nozzle_temperature=_as_text(values.get("nozzle_temperature_initial_layer")),
        generated_at=generated_at,
    )

    return BuildResult(
        gcode=build_looped_gcode(plan),
        profile=profile,
        placement=placement,
        max_layer_z=max_layer_z,
        max_layer_z_from_header=from_header,
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


def _as_text(value: object) -> str | None:
    return str(value) if value else None
