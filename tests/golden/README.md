# Captured output of the original Looprint web tool

Each `webtool_*.gcode.gz` is the `Metadata/plate_1.gcode` that
[`looprint/index.html`](../../../looprint/index.html) produced from
`Gcode/test 2 blocks.gcode.3mf`, captured by running the unmodified page in a
browser against a local file server. The file name encodes the settings:

| File | Loops | Cool-down | Speed |
|---|---|---|---|
| `webtool_n3_t18.gcode.gz` | 3 | 18 °C | 100 % |
| `webtool_n5_t30_s124.gcode.gz` | 5 | 30 °C | 124 % |
| `webtool_n2_t25_s166.gcode.gz` | 2 | 25 °C | 166 % |

All three were A1 Mini (auto-detected from `printer_model_id = N1`).

`test_webtool_equivalence.py` regenerates each one with pylooprint and asserts
equality. The `; Generated:` banner line is normalised away — it is a wall-clock
timestamp and is the only line that legitimately differs between two runs.

To recapture after changing the original tool: serve the repository root over
HTTP, open `looprint/index.html`, load the sample through the file input, set
the controls, press Generate, and pull `finalFileContent` out of the page.
