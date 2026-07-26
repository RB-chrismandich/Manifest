# Verifying a recommendation by slicing it

Settings advice is normally open-loop: you claim four walls and 35% gyroid make
the part stronger, the user prints it, and nobody ever checks what the change
cost. Bambu Studio ships a headless CLI that closes that loop.

`scripts/slice_check.py` wraps it. Both subcommands read the CLI's own
`result.json`, so every number below is reported by the slicer, not estimated.

## What you get back

```
=== saddle_h0.stl · 0.20mm Standard @BBL X1C ===
  applied : layer 0.2 mm · 2 walls · 15.0% infill
  estimate: 40m20s · 16.32 g
  time by feature:
    Sparse infill              13m41s  (34%)
    Outer wall                 10m29s  (26%)
    Inner wall                  8m26s  (21%)
  slicer warning: It seems object saddle_h0.stl has floating cantilever.
                  Please re-orient the object or enable support generation.
```

Four distinct kinds of evidence, each worth something different:

- **`applied`** — proof the preset took effect. A preset can import cleanly and
  still not apply the way it reads (see the H2D per-variant arrays in `h2d.md`).
  This is the only cheap way to catch that.
- **time by feature** — where the minutes actually go. This is what makes a
  trade legible: if 34% of the print is sparse infill, cutting density is the
  lever; if outer wall dominates, it is not.
- **mass** — the denominator for any strength-per-gram argument.
- **slicer warning** — Bambu's own read of the geometry. On the shade-bar saddle
  it independently flagged the floating cantilever that `inspect_model.py`
  measured as 57 mm² of unsupported downward faces. Two tools agreeing from
  different evidence is much stronger than either alone.

## Reading a comparison

```
=== delta (candidate - base) ===
  time : +13m02s  (+32%)
  mass : +15.64 g  (+96%)
  biggest shifts by feature:
    Inner wall                   +827 s
    Sparse infill                -306 s
    Outer wall                   +251 s
```

That is `0.20mm Standard` → `0.20mm Strength` (2 → 6 walls, 15 → 25% infill) on
a 31 cm³ part. Note the sparse infill going *down* by 306 s: extra walls displace
infill volume, so the cost is not the naive sum of both increases. Reasoning
about that from first principles is guesswork; measuring it takes 90 seconds.

Quote the delta in the brief's "trading away" line. It is the difference between
"this will take somewhat longer" and "this costs you 13 minutes and 16 grams."

## The multi-extruder limitation

The CLI **cannot slice for the H2D**, or any multi-extruder machine, from a bare
STL plus preset files. It exits with:

```
plate 1 : some filaments can not be mapped under auto mode for multi extruder printer
return_code: -66
```

This was chased down rather than assumed. What does not fix it:

- passing one filament, or one per extruder (`--load-filaments "a.json;b.json"`)
- `--load-filament-ids`, `--load-defaultfila`, `--estimate-mode`
- exporting a 3MF via the CLI and re-slicing it
- patching `filament_map_mode` from `"Auto For Flush"` to `"Manual"` inside that
  3MF's `project_settings.config` — it then fails under manual mode instead

There is no `--filament-map` or `--filament-colour` option. The mapping is
printer/AMS state the CLI has no way to accept. Single-extruder machines (X1C,
P1S, A1, A1 mini) work end to end.

Two usable options on an H2D:

1. **Pass a 3MF exported from Bambu Studio.** The GUI bakes in the filament and
   nozzle assignment, so the mapping is already valid. Override the process
   preset with `--process` to A/B a candidate against it.
2. **Use a single-extruder proxy** (X1C is closest) purely to measure the
   *relative* effect of a settings change. Absolute times will not match the H2D,
   but the direction and rough magnitude of a delta will. Label it as a proxy
   whenever you do this.

## Gotchas already handled

- **Working directory must be under `$HOME`.** The CLI writes scratch files next
  to the CWD, and macOS denies it access under `/private/tmp`. The symptom is a
  bare `Unable to open the file part.3mf.tmp`, which does not look like a
  permissions problem. `slice_check.py` uses a temp dir in `$HOME`.
- **`--export-3mf` is relative to `--outputdir`.** Passing a path that already
  includes the outputdir yields `./out/./out/part.3mf` and fails.
- **Reported filament mass is `0.00 g`.** The CLI never resolves filament density
  in this mode, and the gcode footer says `total filament weight [g] : 0.00` too.
  `slice_check.py` recovers it from `total filament length [mm]` and the
  filament preset's `filament_density`, resolved up the inheritance chain — the
  leaf preset does not contain it. On the test part this yields 16.3 g against a
  measured 31 cm³ volume at 15% infill, which is the right order.
- **The CLI does not follow `inherits`.** This is the one that silently corrupts
  results. Bambu's presets are deltas: `0.12mm Fine @BBL X1C.json` contains no
  `layer_height` at all — it lives in the ancestor `fdm_process_single_0.12`.
  Hand the CLI that leaf file and it slices at the default 0.2 mm, exits 0, and
  writes valid gcode for a print nobody asked for. `slice_check.py` therefore
  resolves the chain into a flattened temp preset before every run.
  Only the **process** preset is flattened: machine presets carry `include`
  directives pointing at gcode templates resolved relative to the original file,
  so a flattened copy in a temp dir loses them and the run fails with "The
  selected printer is not compatible with the process preset in the 3mf."
- **Give each run its own `--outdir`.** A failed run leaves the previous run's
  `plate_1.gcode` behind, and the next summary would pair a fresh `result.json`
  with stale gcode. `slice_check.py` clears the directory before each slice.
- **`total filament volume [cm^3]` in the gcode is mislabeled** — the figure is
  mm³. Do not quote it as cm³.
