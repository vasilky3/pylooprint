# pylooprint

Console tool for the Bambu Lab A1 Mini: it takes a plate you already sliced in
OrcaSlicer / Bambu Studio and rewrites it so the same part prints many times in
a row, cooling down and ejecting each copy before the next one starts.

```bash
python -m pylooprint "my_part.gcode.3mf"        # one copy that ejects itself
python -m pylooprint "my_part.gcode.3mf" -n 10  # ten in a row
```

Nothing to install; run it from this folder (or `python -m pip install -e .` for
a bare `pylooprint` command).

> **Safety.** This drives a heated printer through an unattended part-ejection
> cycle. Stay in the room. Watch the first loop end-to-end before trusting it.

## How a loop works

The slicer's own machine G-code is kept; only what breaks looping is changed.

* **The start code passes through untouched.** Purging is the job of the
  looping machine profile in `profiles/a1mini/`: instead of the stock purge
  lines it waits for the first-layer nozzle temperature, purges into the air,
  and prints a small **purge wall** on the front lip - two lines along X68..98,
  1.8 mm tall, written as plain G-code for the 0.2 mm profile so it comes out
  the same whatever print profile is selected. A plate sliced with the stock
  profile still loops; it just draws the stock purge lines there instead.
* **The end code gets the eject sequence spliced in.** Everything the slicer
  does first (timelapse, filament unload, hotend off) is kept, then:
  1. the gantry parks up against the top switch (Z184 - deliberately above the
     180 mm printable height, do not "correct" it) and the bed cools to `--temp`;
  2. a **release hold** of `--hold` seconds, nothing moving, so the part keeps
     shrinking off the plate; then one short beep - the only warning that the
     machine is about to move;
  3. the **push**: the toolhead comes down off the plate in the back-left
     corner, crosses at Z0.2 and rises only once it stands on a push line, then
     the bed drives the part into it. One line per part, or per group of parts
     within the blade's reach (50 mm blade x 0.25 overlap = 12.5 mm), left to
     right, each at 70 % of the height of the *shortest* part it covers. By
     default every line first works the part loose with **press-and-swipe
     cycles** measured against the G-code (where the bumper, 30 mm ahead of
     the nozzle, first meets plastic); `-s/--simplepush` is one straight shove;
  4. the **sweep**: four strips across X at bed level (Z0.2), then a shove at
     X83 to Y-5 that knocks the purge wall off the front lip;
  5. on the last copy only, the head goes back to where an ordinary print of
     that plate parks it (read out of the slicer's end code), and the slicer's
     own reset and finish sound close the file.
* **Keep-out corner.** The toolhead body overhangs `X 0-15, Y 150-180` when it
  comes down, so a plate with material there is refused before any G-code is
  written. The check walks the extruded moves themselves (arcs included), not
  a bounding box.

## The looping profile

Import `profiles/a1mini/machine/PLP BBL A1 mini 0.4 nozzle.json` in OrcaSlicer
(*Import Configs*); matching filament and process profiles sit next to it.

The file to edit is `profiles/a1mini/source/start.gcode`, one command per line;
the JSON is written from it by

```bash
python profiles/build_profile.py
```

The test suite fails while the JSON is stale. If the wall moves, `PURGE_WALL_X`
/ `PURGE_SWEEP_Y` in `pylooprint/printers/a1mini/profile.py` have to follow. No
comment in that file may look like a slicer layer marker (`; layer ...`,
`;LAYER_CHANGE`, `; CHANGE_LAYER`, `;Z_HEIGHT`): the plate is split at the first
one, and the rest of the wall would be taken for a part.

## Usage

```bash
python -m pylooprint INPUT.gcode.3mf [-o OUTPUT.gcode.3mf] [-n LOOPS] [-t TEMP] ...
```

| Option | Default | Meaning |
|---|---|---|
| `-n, --loops` | 1 | how many copies |
| `-t, --temp` | 26 | bed temperature to cool down to before the push-off |
| `--hold` | 400 | seconds to wait at the park height before the push-off beep (`0` skips the wait; the beep always sounds) |
| `-s, --simplepush` | off | one straight shove per line instead of the press-and-swipe cycles (tuned by the `ZPUSH_*` constants in `printers/bedslinger.py`) |
| `-p, --printer` | auto | `a1mini`; `a1` is a stub that refuses to build |
| `-o, --output` | `<input>_looped_<n>x.gcode.3mf` | where to write the result |
| `--dry-run` | off | report without writing |

A file that was already looped is refused - loop the original, not the output.

Every run reports what it found and what it will do, so both can be checked
before an unattended batch:

```
printer     : A1 Mini
loops       : 1
model height: 77.40 mm
model box   : X 30.6..147.9  Y 9.6..103.8
parts       : 3
  part 1    : X 8.9..97.6  Y 10.5..77.5  top Z 54.40  (88.7 x 67.0 mm)
  part 2    : X 76.2..103.8  Y 76.2..103.8  top Z 76.40  (27.7 x 27.7 mm)
  part 3    : X 120.6..171.4  Y 9.6..60.4  top Z 33.40  (50.8 x 50.8 mm)
push plan   : 3 line(s), left to right (blade 50 mm, reach 12.5 mm)
  line 1    : X 53.24  Z 38.08  contact Y 70.06  (part 1)
  line 2    : X 90.00  Z 53.48  contact Y 124.14  (part 2)
  line 3    : X 145.99  Z 23.38  contact Y 72.73  (part 3)
push mode   : z-push, 8 cycles (approach 1.0, press 1.0, swipe 2.0 mm)
```

The X, Z and contact figures are the ones written into the G-code. Parts are
found from the geometry: extruded moves within 2 mm of each other are one part,
whatever the slicer's objects say; skirt, brim and prime tower are left out.

## Layout

```
pylooprint/
  cli.py  pipeline.py  settings.py  errors.py
  core/        printer-independent: open the 3MF, split the plate, find the parts,
               plan the push, read the slicer's park, assemble the loops
  printers/
    base.py        PrinterProfile - what a machine has to provide
    bedslinger.py  shared engine for machines whose bed moves in Y
    detection.py   which printer a project was sliced for
    a1mini/        the A1 Mini: profile.py + templates/
    a1/            stub: registered, detected, refuses to build
profiles/
  build_profile.py           writes <printer>/source/start.gcode into the JSON
  a1mini/{machine,filament,process,source}/
tests/  test gcode/          sliced A1 Mini plates the suite runs on
```

**Adding a printer:** a package under `printers/` subclassing `PrinterProfile`
(or `BedSlingerProfile`), an entry in `printers/__init__.py`, its model id in
`detection.py`, a folder under `profiles/`. `printers/a1/profile.py` lists what
the A1 still needs.

## Tests

```bash
python -m pytest
```

* `test_core.py` - splitting a plate, reading arcs, assembling and signing loops.
* `test_parts.py` - the part finder: the 2 mm rule, skirts, arcs, real plates.
* `test_push_plan.py` - one line per part or band, heights, and that the blade
  never descends at a new spot.
* `test_zpush.py` - the press-and-swipe cycles and the measured contact.
* `test_release_hold.py` - the hold moves nothing; the beep always sounds.
* `test_purge_wall.py` - the shove that closes the sweep, at Z0.2.
* `test_parking.py` - the last copy parks where an ordinary print would.
* `test_eject_zone.py` - the keep-out corner, on synthetic and real plates.
* `test_printers.py` - registry, detection, the A1 stub's refusal.
* `test_profile.py` - the Orca profile is built from its source and says what
  the code assumes about the wall.
* `test_cli.py` - end-to-end runs and the report.

MIT.
