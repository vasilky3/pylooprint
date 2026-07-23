# pylooprint

Console-only Python port of [Looprint](../looprint) — it takes a plate you already
sliced in Bambu Studio / OrcaSlicer and rewrites it so the same part prints many
times in a row, cooling down and ejecting each copy before the next one starts.

No web view, no browser, no upload. One command:

```bash
python -m pylooprint "my_part.gcode.3mf" -n 10 -t 18
```

The original project is untouched; this package only *reads* its G-code
templates (they were extracted once into `printers/templates/`).

> **Safety.** This drives a heated printer through an unattended part-ejection
> cycle. Stay in the room. Watch the first loop end-to-end before trusting it.

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
| 5. Drop the machine end code | `structure.py` | Everything from the last `;===== date:` marker is the slicer's end code and must go |
| 6. Split the file | `structure.py` | header / `CONFIG_BLOCK` / setup / print body, cutting the slicer start code out from between `; FEATURE: Custom` and the first layer marker |
| 7. Keep the extruder | `structure.py` | Recover `T0`..`T3`, otherwise the loop inherits `T255` from the unload sequence and never extrudes |
| 8. Read the slicer settings | `config_block.py`, `variables.py` | Parse `CONFIG_BLOCK` into values, with G-code and hard-coded fallbacks |
| 9. Render the templates | `template.py` | `[name]`, `{expression}` and `{if ...}{endif}` substitution, including the `{max_layer_z ± n}` arithmetic |
| 10. Assemble the loops | `loop_builder.py` | Banner, per-loop header/config or `M400`, setup, start code, `M220 S<speed>`, print, end code |
| 11. Repack | `project.py` | Write the new plate G-code back into a copy of the zip |

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
| `-n, --loops` | 5 | how many copies |
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
python -m pylooprint "A1mini_cube10_x3.gcode.3mf" -n 20 -t 18 -o batch.gcode.3mf
```

---

## Tests

```bash
python -m pytest
```

The suite is anchored on real output of the original web tool:

* **`test_webtool_equivalence.py`** — `looprint/index.html` was run unmodified in
  a browser on `Gcode/test 2 blocks.gcode.3mf` at three settings, and its output
  frozen into `tests/golden/`. pylooprint regenerates each one and must match
  **line for line**; the only permitted difference is the `; Generated:`
  wall-clock timestamp, and a second test asserts that nothing else hides behind
  that normalisation.

  | Loops | Cool-down | Speed | Output |
  |---|---|---|---|
  | 3 | 18 °C | 100 % | 448 731 B / 21 046 lines |
  | 5 | 30 °C | 124 % | 720 225 B |
  | 2 | 25 °C | 166 % | 312 984 B |

* **`test_a1_mini_golden.py`** rebuilds the archived `2b_LP.gcode` from
  `2b_base.gcode` (A1 Mini, 1 loop, 58 °C) and asserts it is **byte-for-byte
  identical** — a second, independently produced sample. It also compares the
  generated A1 Mini end code against the one embedded in
  `Gcode/result.gcode.3mf`.
* **`test_loops.py`** runs `Gcode/result.gcode.3mf` through the pipeline at 1, 2
  and 5 loops and checks the per-loop structure.

Tests that need those samples skip themselves if the `Gcode` folder is absent.

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
