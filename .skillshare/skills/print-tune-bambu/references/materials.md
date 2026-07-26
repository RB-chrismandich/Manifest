# Materials: what each family constrains

Always confirm the exact spool with the user before using anything here. "PETG"
and "PETG-CF" differ by a factor of two in flow limit and want different support
gaps and a different nozzle — guessing between them produces confidently wrong
advice.

Numbers below are read from Bambu's own H2D filament presets and are here for
orientation. Re-read the actual preset for the actual spool:

```bash
python3 bambu_profiles.py --kind filament list --printer 'H2D(?!P)'
python3 bambu_profiles.py --kind filament get "Bambu PETG-CF @BBL H2D 0.4 nozzle" \
    nozzle_temperature hot_plate_temp chamber_temperatures filament_max_volumetric_speed \
    fan_max_speed temperature_vitrification filament_dev_ams_drying_temperature
```

## The flow limit is the real speed ceiling

`filament_max_volumetric_speed` (mm³/s) is what actually caps a print, not the
motion system. The H2D can move at 1000 mm/s; PPS-CF can only be melted at
6 mm³/s. At a 0.42 mm line and 0.2 mm layer, each mm/s of print speed consumes
roughly 0.084 mm³/s, so:

| Filament | Flow (std / high-flow) | Rough speed ceiling at 0.42 × 0.2 |
|---|---|---|
| PLA Basic | 25 / 40 | ~300 / 475 mm/s |
| PETG HF | 25 / 40 | ~300 / 475 mm/s |
| ABS | 20 / 35 | ~240 / 415 mm/s |
| ASA | 20 / 35 | ~240 / 415 mm/s |
| PC | 20 / 35 | ~240 / 415 mm/s |
| TPU 95A HF | 12 / 16 | ~140 / 190 mm/s |
| PETG-CF | 11.5 | ~135 mm/s |
| PAHT-CF | 8 | ~95 mm/s |
| PVA | 6 | ~70 mm/s |
| PPS-CF | 6 | ~70 mm/s |

The slicer already clamps to this, so raising a speed above the ceiling changes
nothing except the number in the profile. Recommending it anyway is a tell that
the advice was not grounded — check the flow limit before proposing a speed.

## Per family

### PLA (Basic, Matte, Tough, Silk, Wood, Glow, Marble …)
220 °C / 55 °C bed / no chamber / fan to 80–100 %.
Easy, stiff, brittle, creeps under sustained load, softens around 60 °C.
Do not use for anything in a car, in sun, or under constant load.
- Best overhang behaviour of any family — full cooling is your friend.
- Chamber must stay **open/cool**; a hot chamber softens PLA and jams the hotend.
- Matte and Silk are more brittle than Basic; Tough/Tough+ trade stiffness for
  impact resistance.

### PETG (Basic, HF, Translucent)
245 °C / 70 °C bed / low fan (stock max 30 %).
Tough, water- and UV-tolerant, slightly flexible, good for functional parts.
- Bonds *too well* to smooth PEI — glue stick as a release agent, not as adhesive.
- Welds itself to supports: raise `support_top_z_distance` /
  `support_bottom_z_distance` from 0.2 to 0.22–0.28, and
  `support_object_xy_distance` to ~0.4, or the supports become part of the model.
- Strings when wet or too hot. Dry before blaming retraction.
- Low fan is deliberate; forcing cooling costs layer adhesion.

### ABS / ASA
270 °C / 90–100 °C bed / **chamber heat matters** / fan 35–60 %.
Heat-resistant, machinable, ASA adds UV stability for outdoors.
- Warping is the whole game. Use the H2D's chamber heater, close the doors, brim,
  and keep fan low. Large flat parts warp regardless — design in rounded corners.
- Enable `activate_air_filtration`; styrene fumes are unpleasant and worth venting.
- ASA over ABS for anything that lives outside.

### PC / PC FR
280 °C / 110 °C bed / hot chamber / low fan.
Very strong and heat-resistant; warps harder than ABS and is hygroscopic.
- Dry it. Wet PC prints cloudy, weak and bubbly, and no setting recovers it.
- Needs both chamber heat and a strong first layer; expect brim on anything large.

### Nylon: PA, PA6, PAHT, PA12 (usually CF/GF filled)
290 °C / 100 °C bed / hot chamber / minimal fan / flow only ~8 mm³/s.
Excellent toughness, wear resistance, and fatigue life. The most moisture-sensitive
common material by a wide margin.
- **Dry immediately before printing and keep it dry during.** Unfilled nylon can
  absorb enough moisture in a few hours of room air to ruin a print. This is the
  single most common cause of "PA prints badly" and it is not a settings problem.
- Parts absorb moisture in service too and grow slightly — allow for it on
  tolerance-critical fits.
- The low flow limit means these prints are slow no matter what the profile says.

### Carbon/glass filled (PLA-CF, PETG-CF, PA6-CF, PA6-GF, PPA-CF, PET-CF, PPS-CF)
- **Hardened nozzle required.** Filler grinds a brass nozzle out of spec in
  hours. Confirm the H2D has a hardened nozzle fitted before recommending these.
- Stiffer and more dimensionally stable than the unfilled base, but more brittle
  and weaker between layers — the fibers align in-plane and do nothing across
  layers, so orientation matters *more*, not less.
- Matte surface hides layer lines well.
- Flow limits are roughly half the unfilled equivalent.
- More walls, less infill is the right trade — the fibers work in the walls.

### PPS-CF
320 °C / 110 °C bed / hot chamber / 6 mm³/s.
Chemical- and heat-resistant engineering material. Slow, expensive, demanding;
only recommend when the requirement genuinely calls for it.

### TPU (85A, 90A, 95A, 95A HF)
230–240 °C / 35 °C bed / full fan / 12–16 mm³/s.
Flexible. Softer durometer = harder to print.
- The H2D has a dedicated **Direct Drive TPU High Flow** variant — slot 4 in the
  per-variant arrays. Use it.
- Slow and steady; retraction causes jams, so minimize it
  (`reduce_crossing_wall`, low travel counts).
- 85A generally wants the AMS bypass, not the AMS.
- Infill pattern controls how squishy the part feels as much as density does —
  `gyroid` at low density gives even compliance.

### Support / soluble (PVA, BVOH, Support W/G, Support for PLA / ABS / PA-PET)
- PVA and BVOH dissolve in water; the interface-material approach costs far less
  than printing the whole support tree in soluble filament. Set
  `support_interface_filament` to the soluble one and leave `support_filament`
  as the model material.
- PVA is hygroscopic and slow (6 mm³/s). Dry it.
- Support W/G are break-away, not soluble — cheaper and faster where a hand-
  removable interface is enough.
- On the H2D this is where the second nozzle earns its keep: dedicated support
  material without AMS swap purging on every layer.

## Drying, in one place

`filament_dev_ams_drying_temperature` and `filament_dev_ams_drying_time` in each
filament preset give Bambu's own recommendation (commonly 55–65 °C for 12 h).

Roughly, worst to least affected: PA > PVA/BVOH > PC > PPS-CF > PETG-CF > PETG >
ABS/ASA > PLA.

Wet filament shows up as popping/hissing at the nozzle, stringing, a rough or
foamy surface, and weak layer adhesion. If those symptoms appear together, say
so and recommend drying **before** recommending settings — otherwise the settings
change gets credited or blamed for something it never controlled.
