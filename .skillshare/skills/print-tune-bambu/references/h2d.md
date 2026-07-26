# Bambu Lab H2D specifics

Verify anything here against the local install rather than trusting the page:

```bash
python3 bambu_profiles.py --kind machine get "Bambu Lab H2D 0.4 nozzle" \
    printable_area extruder_printable_area machine_max_acceleration_extruding \
    machine_max_speed_x nozzle_diameter extruder_variant_list
```

## Envelope

- Plate is **350 × 320 mm**, `printable_height` 325 mm, but neither nozzle
  reaches all of it: `extruder_printable_area` gives the left extruder X 0–325
  and the right extruder X 25–350. So a single-material print has a 325 × 320
  window, and a **dual-material print only has the 300 × 320 overlap** (X 25–325).
  A wide two-color part placed against either X edge will fail to slice for one
  of the nozzles.
- Motion: up to 1000 mm/s travel, 20000 mm/s² machine acceleration ceiling.
  Stock profiles run well below this — see the flow-limit discussion in
  `materials.md` for why raising speeds usually achieves nothing.
- Hotend to 350 °C, heated chamber to 65 °C, so ABS/ASA/PA/PC/PPS-CF are all
  genuinely in scope rather than technically-possible.
- Nozzle sizes 0.2 / 0.4 / 0.6 / 0.8, each with its own machine profile and its
  own set of compatible process presets. Changing nozzle means changing the base
  preset, not editing one.

## The per-extruder-variant array

This is the H2D detail that most often produces a broken preset.

On single-extruder Bambu printers, `outer_wall_speed` is a scalar. On the H2D it
is an array with one slot per extruder variant, ordered by
`print_extruder_variant`, which pairs with `print_extruder_id`:

| Slot | `print_extruder_id` | `print_extruder_variant` |
|---|---|---|
| 0 | 1 (left) | Direct Drive Standard |
| 1 | 1 (left) | Direct Drive High Flow |
| 2 | 2 (right) | Direct Drive Standard |
| 3 | 2 (right) | Direct Drive High Flow |
| 4 | 2 (right) | Direct Drive TPU High Flow |

Rules that follow from this:

- Every per-variant override must be **exactly five entries**. Use `"nil"` for
  slots you want left inherited. `bambu_profiles.py validate` enforces the length.
- A bare string (`"outer_wall_speed": "120"`) imports without complaint and then
  does not apply the way it reads. This is the failure worth checking twice.
- Overriding only slot 0 leaves the right nozzle and every high-flow variant at
  stock. That is sometimes right and usually an accident, so state which nozzle
  you assumed the filament is in.
- The stock arrays are not uniform: `outer_wall_speed` is
  `["200","500","200","500","500"]` — the high-flow variants are much faster.
  Copying slot 0's value into all five slots silently halves the machine.

**Filament presets use a different array length.** They are indexed by
`filament_extruder_variant`, which varies per material (PETG-CF has one entry,
PLA Basic two, TPU 95A HF three). Read the filament preset's own
`filament_extruder_variant` before editing a filament-side array; do not assume
five.

## Dual nozzle, prime tower, purging

- `enable_prime_tower` is on by default (`prime_tower_width` 60 mm). It is what
  makes color and material changes clean, and it costs real time and filament.
- Single-material prints do not need it — `enable_prime_tower: "0"` is a
  legitimate saving, and one of the user's own presets does exactly that.
- The "Purge into objects' infill / support" checkboxes (`flush_into_infill`,
  `flush_into_support`, `flush_into_objects`) recycle purge into the model
  instead of the tower. Purging into support is nearly free; purging into infill
  puts the other material inside the part, which matters if the part is
  structural or if colors bleed through thin walls.
- Two nozzles means support material without AMS swaps: set
  `support_interface_filament` to the soluble/breakaway material and leave
  `support_filament` at the model material.
- `standby_temperature_delta` (-5) controls how far the idle nozzle cools. It
  exists to stop the idle nozzle oozing and cooking filament.

## H2D-only process features

- **Infill skin / skeleton.** `skin_infill_density`, `skeleton_infill_density`,
  `skin_infill_depth`, `infill_lock_depth` split the infill volume into a denser
  outer shell and a sparser core. This gives better stiffness per gram than
  raising `sparse_infill_density` uniformly, and it is not available on older
  Bambu machines — so advice copied from X1C guides will not mention it.
- **Height-based slowdown.** `enable_height_slowdown`, `slowdown_start_height`,
  `slowdown_end_height` and friends taper speed as the part gets tall. Useful for
  the tall-and-skinny parts where `inspect_model.py` flags a high aspect ratio.
- **Wrapping detection.** `enable_wrapping_detection` (off by default) watches
  for filament wrapping the nozzle.

## H2D vs H2D Pro

`@BBL H2D` and `@BBL H2DP` are different preset families. When listing presets,
filter with `--printer 'H2D(?!P)'` for the base H2D, or the Pro's presets will be
mixed in and an `inherits` may end up pointing at a preset for a machine the user
does not have — which imports and then reports as incompatible.
