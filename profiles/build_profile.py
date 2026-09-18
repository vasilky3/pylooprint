"""Write the readable start G-code into the machine profile Orca imports.

OrcaSlicer reads a printer profile as strict JSON, and a JSON string cannot hold
a line break - so the start G-code in ``machine/*.json`` is one 10 000-character
line.  The file people edit is ``source/a1mini_start.gcode`` instead, one command
per line, and this script copies it into the JSON.  Nothing is generated or
expanded: the G-code in the JSON is the source, byte for byte.

    python profiles/build_profile.py          # rewrite the JSON from the source
    python profiles/build_profile.py --check  # exit 1 if the JSON is stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "source" / "a1mini_start.gcode"
PROFILE = HERE / "machine" / "PLP BBL A1 mini 0.4 nozzle.json"

#: The profile is a copy of the stock one; renamed and marked as the user's own,
#: or Orca sees a second "Bambu Lab A1 mini 0.4 nozzle" and refuses it.
PROFILE_NAME = "PLP BBL A1 mini 0.4 nozzle"


def build(profile: dict, start_gcode: str) -> dict:
    """The profile with the start G-code and identity fields replaced."""
    updated = dict(profile)
    updated["name"] = PROFILE_NAME
    updated["from"] = "User"
    updated["machine_start_gcode"] = start_gcode
    return updated


def render(profile: dict) -> str:
    """The JSON laid out as Orca writes it - tab-indented, one key per line.

    Matching Orca's own layout keeps a rebuild's diff down to the keys that
    changed instead of every line of the file.  Line endings are LF, which is
    what the repository normalises to.
    """
    return json.dumps(profile, indent="\t", ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="report whether the JSON matches the source")
    args = parser.parse_args(argv)

    on_disk = PROFILE.read_text(encoding="utf-8")
    wanted = render(build(json.loads(on_disk), SOURCE.read_text(encoding="utf-8")))
    stale = on_disk != wanted

    if args.check:
        print(f"{PROFILE.name}: {'stale - run build_profile.py' if stale else 'in sync with the source'}")
        return 1 if stale else 0
    if stale:
        PROFILE.write_text(wanted, encoding="utf-8", newline="\n")
        print(f"wrote {PROFILE.name} from {SOURCE.name}")
    else:
        print(f"{PROFILE.name} already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main())
