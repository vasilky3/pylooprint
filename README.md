# pylooprint

Console-only Python port of [Looprint](../looprint) — it takes a plate you already
sliced in Bambu Studio / OrcaSlicer and rewrites it so the same part prints many
times in a row, cooling down and ejecting each copy before the next one starts.

No web view, no browser, no upload. One command:

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
  over, the gantry parks up against the mechanical switch at the top (Z184.5 —
  deliberately above the 180 mm printable height, do not "correct" it), then the
  cool-down, push-off and wiggle sweep run, and the slicer's own reset and finish
  sound close the loop. The move to the model centre crawls at F300 rather than a
  rapid, so the toolhead cannot knock a tall part over.

Everything the printer profile configured — flow calibration, bed levelling,
build-plate detection — survives untouched.

### Fallback for printers not yet ported

Only the **A1 Mini** has this in-place implementation so far. Any other printer
falls back — with a warning — to the **Factorian templates**: the machine start
and end code are thrown away and replaced with Factorian Designs' start/end
G-code, which is what the original web tool does. This is a stopgap; each printer
loses the fallback as its in-place patches are added.

Either way the loops are assembled by the same code, so the banner, the per-loop
markers and the speed handling are identical — only the machine G-code differs.

---

## Why the structure looks like this

The single-file original mixes UI, printer data and G-code surgery in one
12 000-line script. The port splits it along the line that actually matters:
**what every Bambu printer needs** versus **what one machine needs**.

### Common G-code modifications — `src/pylooprint/core/`

These run identically for a P1, X1, A1 and A1 Mini:

| Step | Module | What it does |
|---|---|---|
| 1. Open the container | `project.py` | A `.gcode.3mf` is a zip; find `Metadata/plate_N.gcode`, keep every other member byte-identical |
| 2. Refuse a re-loop | `constants.py` | Bail out if the file already carries a Looprint watermark |
| 3. Read the model height | `pipeline.py` | `; max_z_height:` from the header — every Z-drop decision depends on it |
| 4. Locate the model | `placement.py` | Scan extrusion moves for the X/Y bounding box, filtering prime lines, nozzle wipes and start-code travel |
| 5. Split the file | `structure.py` | header / `CONFIG_BLOCK` / setup / print body, plus the slicer's machine start and end code kept aside for patching |
| 6. Keep the extruder | `structure.py` | Recover `T0`..`T3`, otherwise the loop inherits `T255` from the unload sequence and never extrudes |
| 7. Read the slicer settings | `config_block.py`, `variables.py` | Parse `CONFIG_BLOCK` into values, with G-code and hard-coded fallbacks |
| 8. Render the templates | `template.py` | `[name]`, `{expression}` and `{if ...}{endif}` substitution, including the `{max_layer_z ± n}` arithmetic |
| 9. Assemble the loops | `loop_builder.py` | Banner, per-loop header/config or `M400`, setup, start code, `M220 S<speed>`, print, end code |
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

### Printer-specific modifications — `src/pylooprint/printers/`

Two engines, because the two families push the part off in *different
directions* and confusing them drives the toolhead into the print:

```
printers/
  base.py          PrinterProfile: the contract (bed, temp offset, start code, end code)
  bedslinger.py    A1 family engine  - bed moves in Y, part is pushed by driving the bed forward
  corexy.py        P1/X1 family engine - bed is fixed, gantry pushes along Y in three X lanes
  a1.py            A1        (N2S)     bed -48..256 x 0..262, 45x M190, optional negative-Z release
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
| Z-drop threshold | 41 mm | 41 mm | 31 mm | 31 mm |
| Sweep | wiggle, always on | wiggle, always on | full bed, opt-in | full bed, opt-in |
| Extras | negative-Z release | — | purge/no-purge start | cutter sequence, aux fan |

Adding a printer means one module plus one entry in `printers/__init__.py`;
nothing in `core/` changes.

---

## Usage

```bash
python -m pylooprint INPUT.gcode.3mf [-o OUTPUT.gcode.3mf] [-n LOOPS] [-t TEMP] ...
```

| Option | Default | Meaning |
|---|---|---|
| `-n, --loops` | 1 | how many copies |
| `-t, --temp` | 18 | bed temperature to cool down to before the push-off |
| `-p, --printer` | auto | `a1`, `a1mini`, `p1`, `x1` — overrides detection |
| `--speed` | 100 | print speed percentage applied to every loop |
| `--push-lane-offset` | 30 | P1/X1: distance of the outer lanes from the model centre |
| `--push-speed` | 300 | P1/X1: push feedrate in mm/min |
| `--sweep` | off | P1/X1: full-bed sweep after the push |
| `--no-purge` | off | P1/X1: start code without the filament flush |
| `--negative-z` | off | A1 only, and only without a Z-axis stiffener mod |
| `--force` | off | process a file that already carries a Looprint marker |
| `--dry-run` | off | report without writing |

Example:

```bash
# twenty copies, ejecting each one, cooling to 18 C first
python -m pylooprint "A1mini_cube10_x3.gcode.3mf" -n 20 -t 18 -o batch.gcode.3mf

# one copy that dismounts itself
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
  align move, multi-loop repetition and speed handling.
* **`test_factorian_fallback.py`** — pins the fallback path: the generated A1
  Mini end code is compared against the one embedded in `Gcode/result.gcode.3mf`
  (byte for byte), and a CoreXY printer is shown to take the fallback and warn.
* **`test_core.py` / `test_printers.py`** — unit coverage of the shared
  machinery (config parsing, structure split, template engine, placement) and of
  what each profile contributes (bed bounds, temp offset, push lanes, sweep).
* **`test_cli.py`** — end-to-end runs through the console entry point.

Tests that need the sample files skip themselves if the `Gcode` folder is absent.

---

## Known differences from the original

* No web UI, no download counter, no Google Translate widget.
* Plain `.gcode` input is not accepted — only `.gcode.3mf`. The original had a
  second, subtly different code path for bare G-code; one path is easier to keep
  correct.
* `--force` exists so an already-looped file can be reprocessed; the web tool
  always refused.

Credit for the automation concept: **Factorian Designs**. Original tool:
**Nicki Andersen**, MIT.
