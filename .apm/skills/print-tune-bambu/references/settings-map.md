# Bambu Studio UI label ↔ config key

Two jobs: tell the user where to click, and write the right key into a preset.
Every key marked **confirmed** below appears in Bambu's own shipped presets, so
`bambu_profiles.py get` will return a real stock value for it. Keys marked
*(candidate)* exist in the binary but no stock preset sets them — verify in the
UI before quoting a "stock value" for one.

Stock values shown are for `0.20mm Standard @BBL H2D` at the time of writing.
**Re-read them with `get` rather than trusting this table** — they move between
Studio releases, and being wrong about a stock value is the fastest way to make
the whole recommendation untrustworthy.

`[×5]` marks a per-extruder-variant array on the H2D. See `h2d.md`.

## Quality

| UI label | Key | Stock | Notes |
|---|---|---|---|
| Layer height | `layer_height` | 0.2 | The single biggest lever on time, strength, and surface |
| Initial layer height | `initial_layer_print_height` | 0.2 | Thicker forgives an imperfect first layer |
| Line width > Default | `line_width` | 0.42 | |
| Line width > Initial layer | `initial_layer_line_width` | 0.5 | Wider = more squish = better adhesion |
| Line width > Outer wall | `outer_wall_line_width` | 0.42 | Narrower sharpens detail, slower |
| Line width > Inner wall | `inner_wall_line_width` | 0.45 | Wider is faster and stronger |
| Line width > Top surface | `top_surface_line_width` | 0.42 | |
| Line width > Sparse infill | `sparse_infill_line_width` | 0.45 | |
| Line width > Internal solid infill | `internal_solid_infill_line_width` | 0.42 | |
| Line width > Support | `support_line_width` | 0.42 | |
| Seam position | `seam_position` | aligned | `aligned`/`nearest`/`back`/`random` |
| Smart scarf seam application | `seam_slope_type` | none | `none`/`external`/`all`; hides the seam by ramping it |
| Scarf application angle threshold | `scarf_angle_threshold` | 155 | |
| Staggered inner seams | `seam_placement_away_from_overhangs` | 0 | |
| Slice gap closing radius | `slice_closing_radius` *(candidate)* | — | |
| X-Y contour compensation | `xy_contour_compensation` | 0 | Shrinks/grows outer contours |
| X-Y hole compensation | `xy_hole_compensation` | 0 | Use for press-fit holes printing undersize |
| Elephant foot compensation | `elefant_foot_compensation` | 0.15 | Note Bambu's spelling |
| Precision > Resolution | `resolution` | 0.012 | |
| Wall generator | `wall_generator` | classic | `classic` or `arachne` (variable width, better thin walls) |
| Order of walls | `wall_infill_order` | inner wall/outer wall/infill | Outer-last = better dimensional accuracy |
| Bridge flow | `bridge_flow` | 1 | Drop toward 0.9 for saggy bridges |
| Thick bridges | `thick_bridges` *(candidate)* | — | |
| Only one wall on top surfaces | `only_one_wall_top` | 1 | |
| Detect overhang wall | `detect_overhang_wall` | 1 | Prerequisite for overhang slowdown |
| Avoid crossing wall | `reduce_crossing_wall` | 0 | Cuts seam scars; costs travel time |
| Smooth speed discontinuity area | `z_direction_outwall_speed_continuous` | 1 | |
| Smooth coefficient | `smooth_coefficient` | 4 | |

## Strength

| UI label | Key | Stock | Notes |
|---|---|---|---|
| Wall loops | `wall_loops` | 2 | The main strength lever; beats infill per gram |
| Alternate extra wall | — *(candidate)* | — | |
| Detect thin wall | `detect_thin_wall` | 0 | |
| Top surface pattern | `top_surface_pattern` | monotonicline | `monotonic` for the cleanest top |
| Top surface density | `top_surface_density` | 100 | |
| Top shell layers | `top_shell_layers` | 5 | Raise when top surfaces pillow |
| Top shell thickness | `top_shell_thickness` | 1.0 | Whichever of layers/thickness is greater wins |
| Bottom surface pattern | `bottom_surface_pattern` | monotonic | |
| Bottom shell layers | `bottom_shell_layers` | 3 | |
| Bottom shell thickness | `bottom_shell_thickness` | 0 | |
| Internal solid infill pattern | — | — | see `sparse_infill_pattern` for sparse |
| Sparse infill density | `sparse_infill_density` | 15% | |
| Sparse infill pattern | `sparse_infill_pattern` | grid | `gyroid` isotropic, `grid`/`cubic` stiff, `lightning` fast |
| Infill/Wall overlap | `infill_wall_overlap` | 15% | Raise to bond infill to walls |
| Infill direction | `infill_direction` | 45 | |
| Minimum sparse infill threshold | `minimum_sparse_infill_area` | 15 | mm² |
| Infill combination | `infill_combination` | 0 | |
| Ensure vertical shell thickness | — | — | |
| Detect floating vertical shells | `detect_floating_vertical_shell` | 1 | |
| Infill lock depth | `infill_lock_depth` | 1.0 | H2D infill skin/skeleton feature |
| Skin infill density | `skin_infill_density` | 15% | Outer shell of the infill volume |
| Skeleton infill density | `skeleton_infill_density` | 15% | Core of the infill volume |
| Skin infill depth | `skin_infill_depth` | 2.0 | mm |

`skin_infill_*` / `skeleton_infill_*` let you run a dense infill skin over a
sparse core — a good strength-per-gram trade on H-series machines that older
Bambu printers cannot do.

## Speed  (all `[×5]`)

| UI label | Key | Stock |
|---|---|---|
| Initial layer | `initial_layer_speed` | 50 |
| Initial layer infill | `initial_layer_infill_speed` | 105 |
| Outer wall | `outer_wall_speed` | 200 / 500 (high flow) |
| Inner wall | `inner_wall_speed` | 300 / 600 |
| Small perimeters | `small_perimeter_speed` | 50% |
| Small perimeter threshold | `small_perimeter_threshold` | 0 |
| Sparse infill | `sparse_infill_speed` | 350 / 600 |
| Internal solid infill | `internal_solid_infill_speed` | 250 / 600 |
| Vertical shell speed | `vertical_shell_speed` | 80% |
| Top surface | `top_surface_speed` | 200 |
| Gap infill | `gap_infill_speed` | 250 |
| Bridge | `bridge_speed` | 50 |
| Overhang speed 25 % | `overhang_1_4_speed` | 0 (= no limit) |
| Overhang speed 50 % | `overhang_2_4_speed` | 50 |
| Overhang speed 75 % | `overhang_3_4_speed` | 30 |
| Overhang speed 100 % | `overhang_4_4_speed` | 10 |
| Totally overhang | `overhang_totally_speed` | 10 |
| Enable overhang speed | `enable_overhang_speed` | 1 |
| Travel | `travel_speed` | 1000 |
| Acceleration > Normal printing | `default_acceleration` | 8000 |
| Acceleration > Outer wall | `outer_wall_acceleration` | 5000 |
| Acceleration > Inner wall | `inner_wall_acceleration` | 0 (= default) |
| Acceleration > Top surface | `top_surface_acceleration` | 2000 |
| Acceleration > Sparse infill | `sparse_infill_acceleration` | 100% |
| Acceleration > Initial layer | `initial_layer_acceleration` | 500 |
| Acceleration > Travel | `travel_acceleration` | 10000 |

Overhang bands are percentages of line width unsupported, not angles: the 100 %
band is an unsupported extrusion. Slowing these is the cheapest fix for drooping
overhangs, and costs almost nothing on a part with few overhangs.

## Support

| UI label | Key | Stock |
|---|---|---|
| Enable support | `enable_support` | 0 |
| Type | `support_type` | tree(auto) |
| Style | `support_style` | default |
| Threshold angle | `support_threshold_angle` | 30 |
| On build plate only | `support_on_build_plate_only` | 0 |
| Support critical regions only | `support_critical_regions_only` *(candidate)* | — |
| Remove small overhangs | `support_remove_small_overhang` *(candidate)* | — |
| Raft layers | `raft_layers` | 0 |
| Support/raft base filament | `support_filament` | 0 (= use current) |
| Support interface filament | `support_interface_filament` | 0 |
| Support wall loops | `tree_support_wall_count` | -1 |
| Top Z distance | `support_top_z_distance` | 0.2 |
| Bottom Z distance | `support_bottom_z_distance` | 0.2 |
| Top interface layers | `support_interface_top_layers` | 2 |
| Bottom interface layers | `support_interface_bottom_layers` | 2 |
| Interface pattern | `support_interface_pattern` | auto |
| Top interface spacing | `support_interface_spacing` | 0.5 |
| Base pattern | `support_base_pattern` | default |
| Base pattern spacing | `support_base_pattern_spacing` | 2.5 |
| Normal support expansion | `support_expansion` | 0 |
| Support/object xy distance | `support_object_xy_distance` | 0.35 |
| Max bridge length | `max_bridge_length` | 0 |
| Independent support layer height | `independent_support_layer_height` *(candidate)* | — |
| Tree branch distance | `support_base_pattern_spacing` | 2.5 |
| Tree branch diameter | `tree_support_branch_diameter` | 2 |
| Tree branch angle | `tree_support_branch_angle` | 45 |

Z distance is the removability dial and it is material-dependent: PETG and TPU
weld to supports at the stock 0.2 mm and want 0.22–0.28; PLA is fine at 0.2 and
can go tighter for a cleaner underside. `support_object_xy_distance` does the
same job horizontally.

## Others

| UI label | Key | Stock |
|---|---|---|
| Skirt loops | `skirt_loops` | 0 |
| Skirt height | `skirt_height` | 1 |
| Skirt distance | `skirt_distance` | 2 |
| Brim type | `brim_type` | (unset — Auto) |
| Brim width | `brim_width` | 5 |
| Brim-object gap | `brim_object_gap` | 0.1 |
| Draft shield | `draft_shield` | disabled |
| Prime tower > Enable | `enable_prime_tower` | 1 |
| Prime tower > Width | `prime_tower_width` | 60 |
| Prime tower > Max speed | `prime_tower_max_speed` | 90 |
| Prime tower > Brim width | `prime_tower_brim_width` | -1 |
| Prime tower > Skip points | `prime_tower_skip_points` *(candidate)* | — |
| Prime tower > Internal ribs | `prime_tower_rib_wall` *(candidate)* | — |
| Spiral vase | `spiral_mode` | 0 |
| Fuzzy skin | `fuzzy_skin` | none |
| Fuzzy skin thickness | `fuzzy_skin_thickness` | 0.3 |
| Fuzzy skin point distance | `fuzzy_skin_point_distance` | 0.8 |
| Fuzzy skin generator mode | `fuzzy_skin_mode` | displacement |
| Ironing type | `ironing_type` | no ironing |
| Ironing flow | `ironing_flow` | 10% |
| Ironing spacing | `ironing_spacing` | 0.15 |
| Ironing speed | `ironing_speed` | 30 |
| Interlocking depth | `interlocking_depth` *(candidate)* | — |
| Reduce infill retraction | `reduce_infill_retraction_mode` | Auto |
| Print sequence | `print_sequence` | by layer |
| Adaptive layer height | `adaptive_layer_height` | 0 |

## Filament-side settings

Temperature, cooling, flow, retraction and drying live in the **filament**
preset, not the process preset. Query them the same way:

```bash
python3 bambu_profiles.py --kind filament get "Bambu PETG-CF @BBL H2D 0.4 nozzle" \
    nozzle_temperature hot_plate_temp chamber_temperature filament_max_volumetric_speed
```

Common filament keys: `nozzle_temperature`, `nozzle_temperature_initial_layer`,
`hot_plate_temp`, `chamber_temperature`, `filament_max_volumetric_speed`,
`filament_flow_ratio`, `filament_retraction_length`, `fan_max_speed`,
`fan_min_speed`, `overhang_fan_threshold`, `slow_down_layer_time`,
`filament_shrink`, `activate_air_filtration`.

## Finding a key you cannot see here

```bash
python3 bambu_profiles.py keys 'ironing'       # search the whole vocabulary
python3 bambu_profiles.py trace "<preset>" <key>   # who set it, and to what
```

If a key comes back only as *candidate*, the reliable confirmation is empirical:
change the option in Bambu Studio, export the preset, and read the exported JSON.
