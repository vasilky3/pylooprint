"""Write the readable start G-code into the machine profile Orca imports.

OrcaSlicer reads a printer profile as strict JSON, and a JSON string cannot hold
a line break - so the start G-code in ``<printer>/machine/*.json`` is one long
line.  The file people edit is ``<printer>/source/start.gcode`` instead, one
command per line, and this script copies it into the JSON byte for byte.

    python profiles/build_profile.py            # rewrite every printer's JSON
    python profiles/build_profile.py a1mini     # one printer
    python profiles/build_profile.py --check    # exit 1 if any JSON is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Printer:
    source: Path
    machine: Path
    #: The profile is a copy of the stock one; renamed and marked as the user's
    #: own, or Orca sees a second copy of the stock name and refuses it.
    name: str


PRINTERS = {
    "a1mini": Printer(
        source=HERE / "a1mini" / "source" / "start.gcode",
        machine=HERE / "a1mini" / "machine" / "PLP BBL A1 mini 0.4 nozzle.json",
        name="PLP BBL A1 mini 0.4 nozzle",
    ),
}


def build(profile: dict, start_gcode: str, name: str) -> dict:
    """The profile with the start G-code and identity fields replaced."""
    updated = dict(profile)
    updated["name"] = name
    updated["from"] = "User"
    updated["machine_start_gcode"] = start_gcode
    return updated


def render(profile: dict) -> str:
    """The JSON laid out as Orca writes it - tab-indented, one key per line, LF."""
    return json.dumps(profile, indent="\t", ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("printers", nargs="*", choices=sorted(PRINTERS), help="default: all")
    parser.add_argument("--check", action="store_true", help="report whether the JSON matches the source")
    args = parser.parse_args(argv)

    stale_any = False
    for key in args.printers or sorted(PRINTERS):
        printer = PRINTERS[key]
        on_disk = printer.machine.read_text(encoding="utf-8")
        wanted = render(build(json.loads(on_disk), printer.source.read_text(encoding="utf-8"), printer.name))
        stale = on_disk != wanted
        stale_any |= stale

        if args.check:
            print(f"{key}: {'stale - run build_profile.py' if stale else 'in sync with the source'}")
        elif stale:
            printer.machine.write_text(wanted, encoding="utf-8", newline="\n")
            print(f"{key}: wrote {printer.machine.name} from {printer.source.name}")
        else:
            print(f"{key}: already in sync")
    return 1 if args.check and stale_any else 0


if __name__ == "__main__":
    sys.exit(main())
