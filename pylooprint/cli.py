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
    DEFAULT_HOLD_SECONDS,
    DEFAULT_LOOPS,
    DEFAULT_TEMP,
    MAX_HOLD_SECONDS,
    MAX_LOOPS,
    MAX_TEMP,
    MIN_HOLD_SECONDS,
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
        "--hold",
        type=int,
        default=DEFAULT_HOLD_SECONDS,
        metavar="SECONDS",
        help=(
            "A1/A1 Mini: seconds to hold at the park height after the cool-down, before "
            f"the push-off beep (default: {DEFAULT_HOLD_SECONDS}; 0 skips the wait, the beep always sounds)"
        ),
    )
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
    if not MIN_HOLD_SECONDS <= args.hold <= MAX_HOLD_SECONDS:
        raise LooprintError(f"--hold must be between {MIN_HOLD_SECONDS} and {MAX_HOLD_SECONDS}")
    if not args.input.exists():
        raise LooprintError(f"{args.input} does not exist")


def _run(args: argparse.Namespace) -> tuple[BuildResult, Path]:
    project = ThreeMfProject.open(args.input)
    profile = get_profile(args.printer) if args.printer else detect_printer(project)

    settings = LoopSettings(loops=args.loops, cooldown_temp=args.temp, hold_seconds=args.hold)

    result = build_loops(project, profile, settings, source_name=args.input.name)

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
    wait = f"{args.hold} s, then the push-off beep" if args.hold else "no wait, push-off beep only"
    print(f"hold        : {wait}")
    print(f"output size : {len(result.gcode) / 1024 / 1024:.1f} MB of G-code")

    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if args.temp >= COOLDOWN_WARNING_THRESHOLD:
        print(
            f"warning: a {args.temp} C cool-down may not release the part; parts can be dragged instead of pushed",
            file=sys.stderr,
        )

    print(f"{'would write' if args.dry_run else 'wrote'}: {destination}")
