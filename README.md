# pylooprint

Console-only Python port of [Looprint](../looprint) — it takes a plate you already
sliced in Bambu Studio / OrcaSlicer and rewrites it so the same part prints many
times in a row, cooling down and ejecting each copy before the next one starts.

No web view, no browser, no upload, nothing to install. One command, run from
this folder:

```bash
python -m pylooprint "my_part.gcode.3mf"
```

That produces one copy that ejects itself when it finishes. Add `-n 10` to print
ten in a row.

The original project is untouched; this package only *reads* its G-code
templates (they were extracted once into `printers/templates/`).

> **Safety.** This drives a heated printer through an unattended part-ejection
> cycle. Stay in the room. Watch the first loop end-to-end before trusting it.

---

## How it loops a plate

Keep the machine G-code the slicer emitted and rewrite only what is wrong for
looping:

* **Purge lines become air purges.** The slicer draws its extrusion-calibration
  line across the front of the plate. On the second and later loops that is
  where the previous part was just ejected from, and the line would be drawn
  onto the plate the next part has to stick to. Both calibration draws become
  `G0 E50 F100` — purge into the air instead.
* **The end code gets an eject sequence spliced in.** Everything the slicer does
  first (timelapse, filament unload, hotend off) is kept, the Z-lift is carried
  over, the gantry parks up against the mechanical switch at the top (Z184 —
  deliberately above the 180 mm printable height, do not "correct" it), then the
  cool-down, the release hold, the push-off and the wiggle sweep run, and the
  slicer's own reset and finish sound close the loop. The move onto a push line
  crawls at F300 rather than a rapid, so the toolhead cannot knock a tall part
  over.
* **The push follows the parts** (A1 / A1 Mini). The toolhead is a blade 55 mm
  wide, and half of it has to sit over a part to carry it off, so one pass
  sweeps everything whose centre is within 27.5 mm of it. Parts are grouped into
  as few such passes as possible and pushed left to right, each pass coming down
  to 70% of the height of the *shortest* part it covers — the blade then touches
  every part of the group instead of passing over the low ones, which is what a
  single pass at the plate's centre and the tallest part's height used to do.
  Between passes the blade lifts above everything still standing before the bed
  comes back for the next one. A plate whose body cannot be measured falls back
  to that single central pass.
* **A release hold sits between the cool-down and the push-off** (A1 / A1 Mini).
  Once the bed reaches its target the printer waits `--hold` seconds, so the part
  keeps shrinking off the plate before anything touches it. Nothing in that block
  moves the machine: the toolhead has to stay parked at Z184, which is what keeps
  a limit-switch fan mod running for the whole hold, and the bed has to stay
  where the eject keep-out zone below was measured for.
* **The last copy ends parked where an ordinary print parks** (A1 / A1 Mini).
  The slicer's own lift and park moves are read out of the file the plate came
  in — `G1 X-13 Y180` on the A1 Mini, with a Z that follows the part (its height
  plus 100 mm, capped at the machine's ceiling) — and replayed once the last part
  is off the plate, lift first, since the sweep leaves the nozzle a millimetre
  above it. The copies before the last one do not bother: the next one starts by
  homing anyway.
* **Every printer beeps right before it pushes** — one short `M1006` tone, the
  same macro the slicer's finish sound uses. The machine has been standing still
  through the cool-down, so the beep is the only warning that it is about to move
  again and throw the part off the plate.

Everything the printer profile configured — flow calibration, bed levelling,
build-plate detection — survives untouched.

### Fallback for printers not yet ported

Only the **A1 Mini** has this in-place implementation so far. Any other printer
falls back — with a warning — to the **Factorian templates**: the machine start
and end code are thrown away and replaced with Factorian Designs' start/end
G-code, which is what the original web tool does. This is a stopgap; each printer
loses the fallback as its in-place patches are added.

Either way the loops are assembled by the same code, so the banner and the
per-loop markers are identical — only the machine G-code differs.

---

## Why the structure looks like this

The single-file original mixes UI, printer data and G-code surgery in one
12 000-line script. The port splits it along the line that actually matters:
**what every Bambu printer needs** versus **what one machine needs**.

### Common G-code modifications — `pylooprint/core/`

These run identically for a P1, X1, A1 and A1 Mini:

| Step | Module | What it does |
|---|---|---|
| 1. Open the container | `project.py` | A `.gcode.3mf` is a zip; find `Metadata/plate_N.gcode`, keep every other member byte-identical |
| 2. Refuse a re-loop | `constants.py` | Bail out if the file already carries a Looprint watermark |
| 3. Read the model height | `pipeline.py` | `; max_z_height:` from the header — every Z-drop decision depends on it |
| 4. Locate the model | `placement.py` | Scan extrusion moves for the X/Y bounding box, filtering prime lines, nozzle wipes and start-code travel |
| 5. Split the file | `structure.py` | header / `CONFIG_BLOCK` / setup / print body, plus the slicer's machine start and end code kept aside for patching |
| 5a. Find the parts | `parts.py` | Cluster the extruded moves into separate parts and measure a box for each |
| 5b. Plan the push | `push_plan.py` | Group the parts into blade-wide bands and give each band an X and a Z, left to right |
| 6. Keep the extruder | `structure.py` | Recover `T0`..`T3`, otherwise the loop inherits `T255` from the unload sequence and never extrudes |
| 7. Read the slicer settings | `config_block.py`, `variables.py` | Parse `CONFIG_BLOCK` into values, with G-code and hard-coded fallbacks |
| 8. Render the templates | `template.py` | `[name]`, `{expression}` and `{if ...}{endif}` substitution, including the `{max_layer_z ± n}` and `{max_layer_z * n}` arithmetic |
| 9. Assemble the loops | `loop_builder.py` | Banner, per-loop header/config or `M400`, setup, start code, `M220 S100`, print, end code |
| 10. Repack | `project.py` | Write the new plate G-code back into a copy of the zip |

Step 8 is where the two strategies part company, and **the profile decides which
one it uses** — the pipeline just calls `profile.build_machine_code(...)` and
takes what it is handed. `PrinterProfile.build_machine_code` renders Factorian's
templates by default; `A1MiniProfile` overrides that single method to patch the
slicer's own machine G-code instead, via `patching.py` — anchor-based line-range
replacement that raises rather than silently mis-patching when an anchor is
missing.

Porting a printer to the in-place strategy therefore means overriding one
method. There is no capability flag to keep in step with it.

### Printer-specific modifications — `pylooprint/printers/`

Two engines, because the two families push the part off in *different
directions* and confusing them drives the toolhead into the print:

```
printers/
  base.py          PrinterProfile: the contract (bed, temp offset, start code, end code)
  bedslinger.py    A1 family engine  - bed moves in Y, part is pushed by driving the bed forward
  corexy.py        P1/X1 family engine - bed is fixed, gantry pushes along Y in three X lanes
  a1.py            A1        (N2S)     bed -48..256 x 0..262, 45x M190, 6-position wiggle sweep
  a1_mini.py       A1 Mini   (N1)      bed -13..180 x 0..185, 50x M190, 4-position wiggle sweep
  p1.py            P1/P1S    (C11)     bed 10..246 x 0..256, 30x M190, splices lanes into Factorian's template
  x1.py            X1/X1C    (BL-P001) same lanes as P1 + filament cutter and aux-fan sequencing
  detection.py     printer_model_id -> profile, with project-settings and header fallbacks
  templates/       the raw start/end G-code blocks, one file each
```

What genuinely differs per machine:

| | A1 | A1 Mini | P1/P1S | X1/X1C |
|---|---|---|---|---|
| Push axis | Y (bed) | Y (bed) | Y (gantry), 3 X lanes | Y (gantry), 3 X lanes |
| Bed X range | −48..256 | −13..180 | 10..246 | 10..246 |
| Bed sensor offset | −4 °C | −4 °C | none | none |
| `M190` repeats | 45 | 50 | 30 | 30 |
| Z-drop | 70% of height, Z0.2 under 6 mm | 70% of height, Z0.2 under 6 mm | top − 30 mm, Z1 under 31 mm | top − 30 mm, Z1 under 31 mm |
| Blade / overlap | 55 mm × 0.5 | 55 mm × 0.5 | declared, unused | declared, unused |
| Push lines | one per part or X band | one per part or X band | 3 fixed lanes | 3 fixed lanes |
| Sweep | wiggle, 6 positions | wiggle, 4 positions | — | — |
| Release hold | yes | yes | — | — |
| Push-off beep | yes | yes | yes | yes |
| Eject keep-out | — | X 0–15, Y 150–180 | — | — |
| Extras | — | in-place patching | splices lanes into Factorian's template | cutter sequence, aux fan |

Adding a printer means one module plus one entry in `printers/__init__.py`;
nothing in `core/` changes.

### The A1 Mini eject keep-out

The A1 Mini push-off parks the nozzle off the plate at X-13 / Y180 and then
drops the toolhead to the push height — as low as Z0.2 for a part under 6 mm.
The nozzle clears the plate, but the toolhead *body*
overhangs the back-left corner by 15 mm in X and 30 mm in Y, so anything printed
in `X 0–15, Y 150–180` is struck on the way down. A build whose model prints
there is refused before any G-code is generated:

```
error: Model cannot be ejected. The safe head-descent zone is occupied. ...
the model prints inside it, at X 8.40, Y 162.10 mm.
```

The check walks the actual extruding moves — whole segments, so a diagonal line
crossing the corner counts even when neither of its ends is inside it. It
deliberately does *not* use the model's bounding box: a plate that reaches the
left edge at the front and the back edge in the middle has a box covering a
corner it never touches, and judging by the box refuses a perfectly good file.
Brim and skirt are material too, so they are measured like anything else.

---

## Usage

```bash
python -m pylooprint INPUT.gcode.3mf [-o OUTPUT.gcode.3mf] [-n LOOPS] [-t TEMP] ...
```

Run it from this folder — there is nothing to install. If you would rather call
it from anywhere as a bare `pylooprint` command, `python -m pip install -e .`
puts it on your PATH while still running the files in this folder (undo with
`python -m pip uninstall pylooprint`). Entirely optional.

| Option | Default                         | Meaning |
|---|---------------------------------|---|
| `-n, --loops` | 1                               | how many copies |
| `-t, --temp` | 26                              | bed temperature to cool down to before the push-off |
| `--hold` | 300                             | A1/A1 Mini: seconds to wait at the park height before the push-off beep (`0` skips the wait; the beep always sounds) |
| `-p, --printer` | auto                            | `a1`, `a1mini`, `p1`, `x1` — overrides detection |
| `-o, --output` | `<input>_looped_<n>x.gcode.3mf` | where to write the result |
| `--dry-run` | off                             | report without writing |

A file that already carries a Looprint watermark is refused — loop the original,
not the output.

Every run (including `--dry-run`) reports what it found on the plate and how it
means to sweep it off, so both can be checked before an unattended batch starts:

```
printer     : A1 Mini
loops       : 1
model height: 77.40 mm
placement   : left (X 30.7..146.6)
parts       : 3
  part 1    : X 8.9..97.6  Y 10.5..77.5  top Z 54.40  (88.7 x 67.0 mm)
  part 2    : X 76.2..103.8  Y 76.2..103.8  top Z 76.40  (27.7 x 27.7 mm)
  part 3    : X 120.6..171.4  Y 9.6..60.4  top Z 33.40  (50.8 x 50.8 mm)
push plan   : 2 line(s), left to right (blade 55 mm, reach 27.5 mm)
  line 1    : X 71.62  Z 38.08  (parts 1, 2)
  line 2    : X 145.99  Z 23.38  (part 3)
```

Those X and Z values are the ones written into the G-code — the report and the
push are planned by the same function, so they cannot drift apart.

The parts are found from the geometry, not from the slicer's object markers: the
extruded moves are clustered, so a single object holding several separate bodies
is reported as several parts — and, the other way round, two objects printed
touching each other are one part, because that is what comes off the plate. Two
lumps count as one only when the plastic itself is within 2 mm, so parts standing
a few millimetres apart — which is how a plate is normally arranged — read as
separate. The skirt, the brim and the prime tower are left out, because a
loop drawn around everything would otherwise fuse the whole plate into one part.

Arc moves (`G2`/`G3`, which the slicer emits when arc fitting is on) are followed
around their curve. A round wall is a single arc whose two ends nearly meet, so
reading it as a straight line would lose the part entirely — that applies to the
eject keep-out check as much as to the part count.

Example:

```bash
# twenty copies, ejecting each one, cooling to 26 C first
python -m pylooprint "A1mini_cube10_x3.gcode.3mf" -n 20 -o batch.gcode.3mf

# one copy that dismounts itself, with a warmer release
python -m pylooprint "A1mini_cube10_x3.gcode.3mf" -t 28
```

---

## Tests

```bash
python -m pytest
```

The suite is anchored on two real reference files:

* **`test_inplace.py`** — the primary. Its reference is
  `Gcode/test 2 blocks gcode/test 2 blocks mymod/Metadata/plate_1.gcode`, the
  slicer output in `test 2 blocks/` patched by hand (air purges + spliced eject
  sequence). pylooprint reproduces that file's **machine start and end code byte
  for byte** from the unmodified slicer file; the loop scaffolding around it is
  Looprint's. Also covers the purge patch, the carried-over Z-lift, the slow
  align move and multi-loop repetition.
* **`test_factorian_fallback.py`** — pins the fallback path: the generated A1
  Mini end code is compared against the one embedded in `Gcode/result.gcode.3mf`
  (byte for byte), and a CoreXY printer is shown to take the fallback and warn.
* **`test_core.py` / `test_printers.py`** — unit coverage of the shared
  machinery (config parsing, structure split, template engine, placement) and of
  what each profile contributes (bed bounds, temp offset, push lanes, wiggle sweep).
* **`test_eject_zone.py`** — the A1 Mini keep-out rule, against three real sliced
  plates in `tests/test gcode/`: a full-plate cube that must be refused, a cube
  shifted clear of the corner, and the plate whose bounding box covers the corner
  while its material stays clear of it.
* **`test_parking.py`** — the final park: read off the slicer's own end code,
  emitted in the last loop only, lift before the relative drop, and after the
  sweep but before the motors are switched off.
* **`test_push_plan.py`** — the push planner: which parts share a line, that a
  line comes down to the shortest part it pushes, that the lines run left to
  right, and that the blade lifts clear before the bed comes back.
* **`test_parts.py`** — the part finder: parts standing close together, the skirt
  that loops around all of them, travel moves crossing the gaps, and the two
  in-repo plates, whose single part has to match the model's own bounding box.
* **`test_release_hold.py`** — the wait and the push-off beep: that the block
  never moves the machine, that every profile beeps before its eject sequence,
  and that the beep survives `--hold 0`.
* **`test_cli.py`** — end-to-end runs through the console entry point.

Tests that need the sample files skip themselves if the `Gcode` folder is absent.

---

## Known differences from the original

* No web UI, no download counter, no Google Translate widget.
* Plain `.gcode` input is not accepted — only `.gcode.3mf`. The original had a
  second, subtly different code path for bare G-code; one path is easier to keep
  correct.
* No per-build tuning of the push-off (lane offset, push speed, print speed,
  full-bed sweep, purge-free start, negative-Z release). Each one is either a
  fixed value or dropped, so there is one code path per printer to keep correct.

Credit for the automation concept: **Factorian Designs**. Original tool:
**Nicki Andersen**, MIT.
