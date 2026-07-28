---
name: print-tune-bambu
description: Recommend Bambu Studio print settings for a part and emit an importable process preset. Use when slicing an STL/3MF, tuning for a material (PLA, PETG-CF, ABS, PA, TPU), fixing a failed print (warping, drooping overhangs, weak layers), or asking what a Bambu Studio setting does. Reads stock values from the local install.
---

# Bambu Studio print settings

Settings advice fails in two ways, and both are avoidable. The first is stating a
stock value that is wrong ("default wall loops is 3" — on this machine it is 2),
which quietly destroys trust in every other number in the answer. The second is
reciting a generic strong/fast/pretty profile that ignores what this particular
part actually has to survive.

So the method here is: pin down the four facts, read the real values off the
user's own Bambu Studio install, measure the actual mesh, then change only the
settings that a named failure mode justifies.

## Pin down four facts before recommending anything

Do not skip this. A settings answer with the wrong material in it is worse than
no answer, because it looks authoritative.

1. **Printer and nozzle.** Default to the **Bambu Lab H2D with a 0.4 mm nozzle**
   unless told otherwise. If the part is abrasive-filled (CF/GF), confirm a
   hardened nozzle is fitted.
2. **Filament — always confirm this, never infer it.** "PETG" and "PETG-CF" want
   different walls, different support gaps, and a different nozzle. If the user
   has not named the exact spool, ask. This is a standing instruction from the
   user of this skill, not a nicety.
3. **What the part has to survive.** Load direction, temperature, UV, water,
   fit tolerance, whether a visible face matters. This is the entire basis for
   every deviation from stock.
4. **What it is allowed to trade away.** Print time, filament, surface finish.
   Without this you cannot rank the changes, and every recommendation collapses
   into "turn everything up."

If facts 2-4 are missing, ask for them in one batched question rather than
guessing or drip-feeding. Then proceed.

## Step 1 — read the real stock values

`scripts/bambu_profiles.py` resolves Bambu Studio's own preset inheritance chain
from the local install. Use it instead of recalling defaults; presets change
between Studio releases and between printers.

```bash
S=~/.claude/skills/print-tune-bambu/scripts

python3 $S/bambu_profiles.py root                      # confirm install + user preset dir
python3 $S/bambu_profiles.py list --printer 'H2D(?!P)' --nozzle 0.4
python3 $S/bambu_profiles.py get "0.20mm Standard @BBL H2D" \
    layer_height wall_loops sparse_infill_density support_threshold_angle
python3 $S/bambu_profiles.py trace "0.20mm Standard @BBL H2D" wall_loops   # which file set it
python3 $S/bambu_profiles.py resolve "0.20mm Standard @BBL H2D"            # all ~198 keys
python3 $S/bambu_profiles.py keys 'support.*overhang'                      # find a key by name
python3 $S/bambu_profiles.py user-list                                     # user's own presets
```

`keys` marks each hit CONFIRMED (some stock preset sets it, so `get` returns a
real stock value) or candidate (the key exists in Studio's option table but no
preset overrides it, so there is no stock value to quote). Do not present a
candidate key's value as "stock".

Also run `user-list` early. If the user already keeps a preset for this material
(they may have, for example, a PETG-CF one), inheriting from or aligning with it
respects tuning they already trust, and reveals their house style.

Filament-side values (nozzle temp, bed temp, chamber, cooling, flow, shrink) live
in the filament preset: add `--kind filament`.

## Step 1b — consult the official wiki when the question is not a number

The preset files tell you what a setting *is set to*. They do not tell you what
Bambu says a setting is *for*, or how to diagnose a symptom. `wiki_sync.py` keeps
a local Markdown mirror of wiki.bambulab.com for exactly that.

```bash
python3 $S/wiki_sync.py status                 # is the mirror stale?
python3 $S/wiki_sync.py sync                   # fetch only what changed
python3 $S/wiki_sync.py grep 'first layer'     # search the local mirror
python3 $S/wiki_sync.py show software/bambu-studio/layer-height
python3 $S/wiki_sync.py search 'PETG warping'  # live wiki search index
python3 $S/wiki_sync.py hms 0300_9500_0001_0005 --show   # printer error code
```

`hms` normalizes whatever form the code arrives in — `HMS_0300-9500-0001-0005`,
lowercase hex, or a partial `0300_9500` — because the printer screen, the wiki
paths, and the page titles all format it differently. It ranks H2D-family pages
first, since the same code is documented per model with different steps.

**Staleness is handled for you.** A `PreToolUse` hook on the `Skill` tool runs
`wiki_sync.py autorefresh` whenever this skill is invoked. It is throttled to one
check per 24 h (a timestamp file short-circuits the rest at ~0.1 s), the check
itself is a single GraphQL request, and if pages have changed it starts the sync
detached and tells you so via injected context rather than blocking the turn.

So do not run `status` reflexively. Read the injected note instead: if it says a
background refresh just started, the new text is *not* in this turn's mirror —
either re-read the page after it lands or flag the answer as possibly stale.
Run `sync` yourself only when you need the fresh text right now.

Prefer `grep`/`show` over `search`, since the mirror is local, complete for its
scope, and quotable.

The mirror is scoped by default to the sections that answer settings questions
(`software`, `bambu-studio`, `knowledge-sharing`, `filament`, `filament-acc`,
`h2`, `h2d`, `h2d-pro`, `general`, `ams*`, `parts-acc`, `studio-handy`, `miniwiki`) — about 1000 of the wiki's ~2500 English pages, ~10 MB. Use
`--section x1,p1` or `--all-sections` when a question falls outside that.

When wiki guidance and a stock preset value disagree, the preset wins for "what
is it set to" and the wiki wins for "what does it mean" — and it is worth saying
which one you used.

## Step 2 — measure the model, do not eyeball it

If a file was provided, run it. Claims like "steep overhangs" or "tall and tippy"
should come from numbers, so the recommendation can cite them.

```bash
python3 $S/inspect_model.py --pretty part.stl     # .stl / .3mf / .obj, add nothing else
```

It reports bounding box, volume, bed-contact area, downward-face area split by
slope band (Bambu's threshold-angle convention: 0° = flat down, 90° = vertical),
bridge spans, tipping aspect ratio, and watertightness.

Read the flags first. A **non-watertight mesh is a stop sign** — no amount of
setting tuning fixes missing walls or phantom infill, so say so and point at the
repair before continuing. And note that bed contact and true bridges are excluded
from `support_needed_area_mm2` on purpose: a flat bottom face is not an overhang,
and a bridge anchored at both ends usually wants bridge tuning, not supports.

STEP and other CAD formats are not mesh formats and cannot be measured here — ask
for an exported STL/3MF, or work from the description.

If no file was provided, work from the description and say plainly which
geometric premises you assumed.

## Step 2b — verify by slicing, when the printer allows it

A recommendation nobody measured is an assertion. `slice_check.py` drives Bambu
Studio's headless CLI and reads back what the slicer *actually* did: the applied
layer height, wall count and infill, predicted time broken down by feature,
filament mass, and the slicer's own geometry warnings.

```bash
python3 $S/slice_check.py check part.stl \
    --machine "Bambu Lab X1 Carbon 0.4 nozzle" \
    --process "0.20mm Standard @BBL X1C" --filament "Bambu PLA Basic @BBL X1C"

python3 $S/slice_check.py compare part.stl \
    --machine "Bambu Lab X1 Carbon 0.4 nozzle" --filament "Bambu PLA Basic @BBL X1C" \
    --base "0.20mm Standard @BBL X1C" --candidate "0.20mm Strength @BBL X1C"
```

`compare` is the one that earns its keep — it turns "more walls costs some time"
into "+32% time, +96% mass, inner wall +827 s, sparse infill −306 s". That is the
trade the user was asked to accept, stated in the units they care about.

**The H2D cannot be sliced this way.** The CLI has no flag to map filaments to
nozzles, so any multi-extruder machine fails with `return_code -66`. Single-
extruder machines (X1C, P1S, A1) work completely. On an H2D either pass a **3MF
exported from Bambu Studio**, which carries the mapping the GUI assigned, or
slice a single-extruder proxy and report the delta as *relative*. If you use a
proxy, say so — a proxy number presented as an H2D number is exactly the kind of
confident-wrong claim this whole skill exists to avoid.

## Step 3 — choose the base preset, then change as little as possible

Pick the stock preset whose layer height already matches the job, and inherit
from it. A short delta is reviewable, survives Studio updates, and makes the
reasoning legible. A 60-key profile that reimplements the stock preset is not.

Rough starting points on the H2D 0.4 nozzle — confirm against `list`:

| Job | Base |
|---|---|
| Everyday / prototype | `0.20mm Standard @BBL H2D` |
| Load-bearing, layer adhesion matters | `0.20mm Balanced Strength @BBL H2D` |
| Visible surface, fine detail | `0.12mm Fine @BBL H2D` or `0.16mm Balanced Quality @BBL H2D` |
| Miniature / tiny features | `0.08mm Extra Fine @BBL H2D` |
| Bulk, speed over looks | `0.24mm Standard @BBL H2D` |

## Step 4 — derive each change from a failure mode

For every setting you touch, you should be able to finish the sentence "without
this, the part will ___". If you cannot, drop the change.

`references/failure-modes.md` maps symptoms and requirements to the specific
levers, with the reasoning for each. Read it when you need more than layer
height and walls. `references/settings-map.md` maps the Bambu Studio UI label to
the JSON key, which you need to write the preset and to tell the user where to
click. `references/materials.md` covers what each family constrains.

Two habits that separate good advice from generic advice:

- **Reach for geometry and orientation before settings.** Rotating a part 90° can
  delete the supports, fix the layer-line direction on a load path, and halve the
  time. If that is the real answer, lead with it, then give settings for the
  chosen orientation.
- **Strength is anisotropic.** Walls carry load along the layer; layers are the
  weak plane. For a loaded part, more `wall_loops` beats more
  `sparse_infill_density` per gram almost every time, and orientation beats both.

## Step 5 — deliver both artifacts

Produce a decision brief with a delta table, **and** an importable preset JSON.
The table is what gets read and argued with; the JSON is what gets used.

### The brief

```markdown
## <part> — <material> on <printer> <nozzle>

**Base preset:** `<exact preset name>`
**Filament preset:** `<exact filament preset name>`
**Optimizing for:** <the stated priority> · **trading away:** <the stated cost>

### What the geometry says
<3-5 bullets citing measured numbers, or the assumed premises if no file>

### Changes

| Bambu Studio location | Setting | Stock | Set to | Why |
|---|---|---|---|---|
| Quality > Layer height | Layer height | 0.20 | 0.12 | <failure mode avoided> |

### Left at stock on purpose
<the tempting knobs you did not turn, and why — this is the part that keeps
the profile honest and short>

### Watch for
<what to check on the first print, and what to change if it goes wrong>
```

### The preset JSON

Match Bambu Studio's own export format exactly — a delta with `inherits`, not a
full config:

```json
{
  "name": "PETG-CF bracket 0.16",
  "print_settings_id": "PETG-CF bracket 0.16",
  "inherits": "0.16mm Balanced Quality @BBL H2D",
  "from": "User",
  "version": "<match the version field of an existing user preset>",
  "wall_loops": "5",
  "sparse_infill_density": "30%",
  "outer_wall_speed": ["nil", "nil", "120", "nil", "nil"]
}
```

**The H2D per-variant array is the thing that goes wrong.** On dual-nozzle
machines, every speed and acceleration key is an array with one slot per extruder
variant — five slots on the H2D, in the order given by `print_extruder_variant`:

| Slot | Extruder | Variant |
|---|---|---|
| 0 | left (1) | Direct Drive Standard |
| 1 | left (1) | Direct Drive High Flow |
| 2 | right (2) | Direct Drive Standard |
| 3 | right (2) | Direct Drive High Flow |
| 4 | right (2) | Direct Drive TPU High Flow |

`"nil"` means "inherit this slot". Writing `"outer_wall_speed": "120"` as a bare
string, or an array of the wrong length, produces a preset that imports but does
not apply the way it reads. Set the slots for the nozzle the filament is actually
loaded in, and say in the brief which nozzle you assumed.

## Step 6 — validate before handing it over

```bash
python3 $S/bambu_profiles.py validate /path/to/new-preset.json
```

This checks the required fields, that `inherits` names a preset that exists in
this install, that every key appears in the base chain, and that per-variant
arrays are the right length. Fix errors before presenting; surface warnings in
the brief if they are intentional.

To install it (only when the user asks — it writes into their Studio data dir,
and Bambu Studio must be restarted to see it):

```bash
python3 $S/bambu_profiles.py install /path/to/new-preset.json --yes
```

Otherwise just write the file somewhere convenient and tell them to use
Bambu Studio's **Process preset dropdown > Import** (or drop it in the directory
that `root` printed).

## Things that make the advice worse

- Turning knobs without a named failure mode. Every extra line in the delta is a
  future debugging surface.
- Quoting a stock value from memory when `get` would have taken two seconds.
- Recommending supports for a flat face that is sitting on the build plate.
- Ignoring the filament preset. Warping, stringing, and layer adhesion are more
  often temperature, cooling, and drying than they are process settings — and
  those live on the filament side.
- Maxing speed on the H2D because it can do 1000 mm/s travel. The limit for a
  given print is volumetric flow, cooling, and part rigidity, not the motion
  system.
- Silently assuming which nozzle the material is in on a dual-nozzle machine.

## Reference files

- `references/failure-modes.md` — symptom or requirement → the lever that fixes
  it, and why. Read this for anything beyond layer height and walls.
- `references/settings-map.md` — Bambu Studio UI label ↔ JSON key, grouped by
  the page it lives on. Read this when writing a preset or telling someone where
  to click.
- `references/materials.md` — what each filament family constrains: temperature,
  chamber, drying, abrasion, support strategy, failure signature.
- `references/h2d.md` — H2D hardware envelope, dual-nozzle and prime-tower
  behavior, and the per-variant array convention in full.
- `references/wiki-mirror.md` — how the wiki mirror works, what the GraphQL
  endpoint does and does not expose, HMS lookup, image mirroring costs, the
  weekly refresh agent, and how to point a RAG index at it.
- `references/slice-verification.md` — what the headless slicer reports, how to
  read a comparison, and the multi-extruder limitation in detail.
