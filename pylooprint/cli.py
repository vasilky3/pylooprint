"""Console entry point."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .core.project import ThreeMfProject
from .errors import LooprintError
from .pipeline import BuildResult, build_loops, detect_printer
from .printers import available_profiles, get_profile
from .settings import (
    COOLDOWN_WARNING_THRESHOLD,
    DEFAULT_LOOPS,
    DEFAULT_PUSH_LANE_OFFSET,
    DEFAULT_PUSH_SPEED,
    DEFAULT_SPEED_MODE,
    DEFAULT_SWEEP_SPEED,
    DEFAULT_SWEEP_Z,
    DEFAULT_TEMP,
    MAX_LOOPS,
    MAX_TEMP,
    MIN_LOOPS,
    MIN_TEMP,
    LoopSettings,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pylooprint",
        description=(
            "Loop a sliced Bambu Lab plate so it prints the same part many times, "
            "ejecting each one before the next starts."
        ),
        epilog="Never leave a looping printer unattended.",
    )
    parser.add_argument("input", type=Path, help="sliced .gcode.3mf exported from Bambu Studio / OrcaSlicer")
    parser.add_argument("-o", "--output", type=Path, help="output .3mf (default: <input>_looped_<n>x.3mf)")
    parser.add_argument(
        "-n", "--loops", type=int, default=DEFAULT_LOOPS, help=f"number of copies (default: {DEFAULT_LOOPS})"
    )
    parser.add_argument(
        "-p",
        "--printer",
        choices=sorted(available_profiles()),
        help="override the printer detected from the project",
    )
    parser.add_argument(
        "-t",
        "--temp",
        type=int,
        default=DEFAULT_TEMP,
        help=f"bed temperature to cool down to before the push-off (default: {DEFAULT_TEMP})",
    )
    parser.add_argument(
        "--speed",
        type=int,
        default=DEFAULT_SPEED_MODE,
        help=f"print speed percentage applied to every loop (default: {DEFAULT_SPEED_MODE})",
    )

    corexy = parser.add_argument_group("P1 / X1 only")
    corexy.add_argument(
        "--push-lane-offset",
        type=float,
        default=DEFAULT_PUSH_LANE_OFFSET,
        help=f"distance of the outer push lanes from the model centre (default: {DEFAULT_PUSH_LANE_OFFSET})",
    )
    corexy.add_argument(
        "--push-speed",
        type=float,
        default=DEFAULT_PUSH_SPEED,
        help=f"push-off feedrate in mm/min (default: {DEFAULT_PUSH_SPEED})",
    )
    corexy.add_argument("--sweep", action="store_true", help="add a full-bed sweep after the push-off")
    corexy.add_argument("--sweep-speed", type=float, default=DEFAULT_SWEEP_SPEED)
    corexy.add_argument("--sweep-z", type=float, default=DEFAULT_SWEEP_Z)
    corexy.add_argument(
        "--no-purge",
        action="store_true",
        help="use the start code that skips the filament flush",
    )

    a1 = parser.add_argument_group("A1 only")
    a1.add_argument(
        "--negative-z",
        action="store_true",
        help="add the negative-Z release sequence (only without a Z-axis stiffener mod)",
    )

    parser.add_argument("--force", action="store_true", help="loop a file that already carries a Looprint marker")
    parser.add_argument("--dry-run", action="store_true", help="report what would be built without writing a file")
    parser.add_argument("--version", action="version", version=f"pylooprint {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _validate(args)
        result, destination = _run(args)
    except LooprintError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    _report(args, result, destination)
    return 0


def _validate(args: argparse.Namespace) -> None:
    if not MIN_LOOPS <= args.loops <= MAX_LOOPS:
        raise LooprintError(f"--loops must be between {MIN_LOOPS} and {MAX_LOOPS}")
    if not MIN_TEMP <= args.temp <= MAX_TEMP:
        raise LooprintError(f"--temp must be between {MIN_TEMP} and {MAX_TEMP}")
    if not args.input.exists():
        raise LooprintError(f"{args.input} does not exist")


def _run(args: argparse.Namespace) -> tuple[BuildResult, Path]:
    project = ThreeMfProject.open(args.input)
    profile = get_profile(args.printer) if args.printer else detect_printer(project)

    settings = LoopSettings(
        loops=args.loops,
        cooldown_temp=args.temp,
        speed_mode=args.speed,
        push_lane_offset=args.push_lane_offset,
        push_speed=args.push_speed,
        sweep_enabled=args.sweep,
        sweep_speed=args.sweep_speed,
        sweep_z=args.sweep_z,
        purge_enabled=not args.no_purge,
        negative_z_enabled=args.negative_z,
    )

    result = build_loops(
        project, profile, settings, source_name=args.input.name, force=args.force
    )

    destination = args.output or _default_output(args.input, args.loops)
    if not args.dry_run:
        project.save_as(destination, result.gcode)
    return result, destination


def _default_output(source: Path, loops: int) -> Path:
    stem = source.name
    for suffix in (".gcode.3mf", ".3mf"):
        if stem.lower().endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return source.with_name(f"{stem}_looped_{loops}x.gcode.3mf")


def _report(args: argparse.Namespace, result: BuildResult, destination: Path) -> None:
    print(f"printer     : {result.profile.name}")
    print(f"loops       : {args.loops}")
    print(f"model height: {result.max_layer_z:.2f} mm" + ("" if result.max_layer_z_from_header else " (fallback)"))
    if result.placement:
        print(f"placement   : {result.placement.direction} (X {result.placement.min_x:.1f}..{result.placement.max_x:.1f})")
    print(f"cool-down   : {args.temp} C -> commanded {result.profile.apply_temp_offset(args.temp)} C")
    print(f"output size : {len(result.gcode) / 1024 / 1024:.1f} MB of G-code")

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if args.temp >= COOLDOWN_WARNING_THRESHOLD:
        print(
            f"warning: a {args.temp} C cool-down may not release the part; parts can be dragged instead of pushed",
            file=sys.stderr,
        )

    print(f"{'would write' if args.dry_run else 'wrote'}: {destination}")
