# Failure modes → the lever that fixes them

Organized by what the user actually says, because that is what you get handed.
Each entry names the mechanism first — if the mechanism does not match the case
in front of you, the listed setting will not help either, and you should keep
looking rather than turn the knob anyway.

Ordering within each entry is deliberate: the first fix is usually the one with
the best cost/benefit, and the later ones cost time, material, or finish.

---

## "It broke / it needs to be strong"

**Mechanism.** FDM parts are laminated. Within a layer, strength is roughly the
filament's own; across layers it is the strength of a partial weld, typically
40–70 % of that. So the load path relative to the layer plane dominates every
setting you could change.

1. **Reorient so the load runs along the layers, not across them.** Free, and
   worth more than every setting below combined. Say this first when it applies.
2. `wall_loops` 2 → 4–6. Walls are continuous extrusions carrying load in-plane;
   this is the best strength per gram and per minute available.
3. `sparse_infill_density` 15 % → 30–40 %, and only after walls. Past ~40 % you
   are paying a lot of time for a little stiffness; solid is almost never right.
4. `sparse_infill_pattern` → `gyroid` (isotropic, good under multi-axis load) or
   `cubic`. `grid` is stiff in-plane but weaker diagonally.
5. `infill_wall_overlap` 15 % → 25–30 % so the infill actually bonds to the walls
   instead of resting against them.
6. Filament side: raise `nozzle_temperature` 5–10 °C and cut cooling. Hotter and
   slower welds layers better. This is the highest-leverage change for Z strength
   and it lives in the filament preset, so it is easy to forget.
7. `layer_height` down slightly — more layers means more interfaces but each weld
   is better and the cross-section is more uniform. Modest effect; do it last.

## "It has to hold water / be airtight"

1. `wall_loops` ≥ 4 and `bottom_shell_layers` ≥ 5 — leaks are almost always
   through walls, not infill.
2. `sparse_infill_density` ≥ 25 % so top layers have something to bridge onto.
3. `layer_height` 0.20 → 0.12–0.16. Thinner layers squash together better.
4. Consider `spiral_mode` for a simple open vessel: one continuous wall with no
   seam at all, which is as watertight as FDM gets. Only works for single-wall,
   no-top geometry.
5. PETG holds water better than PLA — it is less brittle and less porous at the
   seam. Worth raising as a material suggestion.

## "Overhangs are drooping / curling"

**Mechanism.** An unsupported extrusion is a rope of hot plastic. It sags until
it freezes. Cooling and time-at-temperature are the levers; supports are the
fallback when geometry leaves no choice.

1. `overhang_2_4_speed` / `overhang_3_4_speed` / `overhang_4_4_speed` down
   (stock 50/30/10 mm/s → 30/20/10). Confirm `enable_overhang_speed` is 1 and
   `detect_overhang_wall` is 1, or none of it applies.
2. Filament side: `overhang_fan_threshold` and `fan_max_speed` up. PLA tolerates
   100 % fan; ABS/ASA/PC do not, and forcing it there causes layer splitting —
   which is why the same fix helps one material and ruins another.
3. `support_threshold_angle` 30 → 20–25 only if you actually want more supports.
4. `support_type` `tree(auto)` for organic/curved overhangs — less contact, easier
   removal, less scarring. `normal(auto)` under flat shelves where tree branches
   would have nothing to grip.
5. Reorient. A 45° rotation frequently deletes the problem outright.

## "The bridge sags"

1. `bridge_flow` 1 → 0.9–0.95. Less plastic in a span that has nothing to rest on.
2. `bridge_speed` up a little (50 → 60–80). Faster spans stretch and cool before
   they can sag — the opposite of the overhang fix, because a bridge is anchored
   at both ends and under tension.
3. Filament side: full cooling over the bridge layer.
4. `internal_bridge_support_thickness` for internal bridges over infill.
5. `max_bridge_length` > 0 to force supports beyond a span you do not trust.
   `inspect_model.py` reports the actual longest span, so use that number.

## "The first layer won't stick / corners lift / it warped"

**Mechanism.** Warping is differential shrinkage: the part cools and contracts
unevenly and peels itself off the plate. Adhesion aids fight the symptom; heat
management fights the cause.

1. `brim_type` → `outer_only`, `brim_width` 5 → 8–10 for tall or small-footprint
   parts. `inspect_model.py` gives bed contact area; under ~100 mm² a brim is
   nearly always right.
2. `initial_layer_print_height` 0.2 → 0.25 and `initial_layer_line_width` 0.5 →
   0.6: more squish, more contact.
3. `initial_layer_speed` 50 → 30.
4. Filament side and more important for ABS/ASA/PA/PC: raise `chamber_temperature`
   and cut cooling on the first layers. On the H2D the active chamber heater is
   the real fix — settings alone will not save a large ABS part in a cold chamber.
5. `elefant_foot_compensation` if the base is *splaying* rather than lifting;
   that is over-squish, the opposite problem, and more brim makes it worse.
6. Physical, not slicer: clean plate, right plate for the material, glue stick for
   PETG (which otherwise bonds to smooth PEI hard enough to chip it).

## "Layers are separating / it delaminates"

1. Filament side first: `nozzle_temperature` up 10 °C, `fan_max_speed` down.
2. **Dry the filament.** PA, PC, PETG-CF, PPS-CF absorb moisture fast, and wet
   filament produces exactly this failure plus stringing and a rough surface.
   No slicer setting substitutes for drying.
3. `chamber_temperature` up for ABS/ASA/PC/PA — slower cooling means a better weld.
4. `layer_height` down slightly.
5. Slow `inner_wall_speed` / `outer_wall_speed`; more time at temperature.

## "The surface looks bad"

Match the fix to which surface:

- **Top surfaces pillowing or rough:** `top_shell_layers` 5 → 6–7,
  `sparse_infill_density` up so tops have support, `top_surface_pattern` →
  `monotonic`, `ironing_type` → `top` for a glassy finish (slow).
- **Vertical wall banding / ringing:** `outer_wall_speed` and
  `outer_wall_acceleration` down (200 → 120, 5000 → 2000–3000). Check the part is
  not tall and skinny — `inspect_model.py` reports aspect ratio; above ~4:1 the
  part itself is ringing and no speed setting fully fixes it.
- **Visible seam:** `seam_position` → `back` if there is a hidden side,
  `seam_slope_type` → `external` (scarf seam) to ramp it away,
  `wall_infill_order` → outer wall last.
- **Blobs and zits:** `reduce_crossing_wall` → 1, and check retraction on the
  filament side.
- **Scarring from travel:** `reduce_crossing_wall` → 1.

## "It's too slow"

Only after establishing what may be traded away.

1. `layer_height` 0.20 → 0.24–0.28. Nearly linear time saving; the single biggest
   lever by a wide margin.
2. `sparse_infill_density` down, or `sparse_infill_pattern` → `lightning` if the
   infill is only holding up the top skin.
3. `wall_loops` down to 2 — but not on anything structural.
4. Larger nozzle (0.6/0.8) if the detail allows. This means a different base
   preset and a different filament preset, not a tweak.
5. Speeds last. Stock H2D speeds are already near the flow limit for most
   materials, so raising them mostly produces under-extrusion rather than a
   faster print.

## "Holes are undersize / it doesn't fit"

**Mechanism.** Inner contours print small because of extrusion width geometry and
material shrinkage, and the error is roughly constant, not proportional. So
scaling the model is the wrong fix.

1. `xy_hole_compensation` — positive to enlarge holes. 0.05–0.15 mm typical.
2. `xy_contour_compensation` for outer dimensions.
3. `wall_generator` → `arachne`, which handles thin and variable-width walls far
   better than `classic`.
4. Print a test coupon rather than iterating on the real part; the correction is
   material- and printer-specific and worth measuring once.

## "It's stringy"

Mostly the filament preset: retraction length/speed, temperature down 5–10 °C,
and drying. On the process side, `reduce_crossing_wall` → 1 and
`travel_speed` up help. For multi-material prints, check prime tower and purge
volumes before blaming retraction.

## "Small features / text won't print"

1. Smaller nozzle (0.2) — a different base preset.
2. `layer_height` down.
3. `wall_generator` → `arachne`, which prints features narrower than one line
   width instead of dropping them.
4. `detect_thin_wall` → 1.
5. `small_perimeter_speed` down.
6. Check the mesh first: `inspect_model.py` will tell you if the feature is even
   present and watertight. Missing detail is often a modelling or export problem,
   and no slicer setting recovers geometry that is not in the file.
