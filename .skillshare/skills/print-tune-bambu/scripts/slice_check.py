#!/usr/bin/env python3
"""Slice a model headlessly and report what the slicer actually did.

Settings advice is otherwise open-loop: you assert that four walls and 35% gyroid
make a part stronger, and nobody checks. Bambu Studio ships a CLI that slices
without a display and writes a machine-readable `result.json` containing the
settings it actually applied, the predicted print time broken down by feature,
filament consumed, and its own warnings about the geometry. That turns a
recommendation into a measurement.

    check    slice once and summarize
    compare  slice the same model under two process presets and diff them

Both read `result.json`, so "outer wall time went from 645 s to 1130 s" is a fact
rather than an estimate.

## A real limitation, worth knowing before you rely on this

The CLI cannot slice for the **H2D or any other multi-extruder machine** from a
bare STL plus preset files. It fails with return code -66, "Some filaments cannot
be mapped to correct extruders for multi-extruder Printer", because the mapping
from filament to nozzle is printer state the CLI has no flag to supply — there is
no --filament-map or --filament-colour option, and patching `filament_map_mode`
inside an exported 3MF does not satisfy it either.

Single-extruder machines (X1C, P1S, A1, A1 mini) work completely.

So on an H2D, use this in one of two ways:
  * Pass a **3MF exported from Bambu Studio**, where the filament/nozzle
    assignment is already baked in by the GUI (`--project part.3mf`).
  * Or slice against a single-extruder proxy printer to compare the *relative*
    effect of a settings change. Times will not match the H2D, but the direction
    and rough magnitude of a delta will. Say which you did — a proxy number
    presented as an H2D number is exactly the kind of confident-but-wrong claim
    this script exists to prevent.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

BINARY_CANDIDATES = [
    "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio",
    "C:/Program Files/Bambu Studio/bambu-studio.exe",
    "/usr/bin/bambu-studio",
]
PROFILES_CANDIDATES = [
    "/Applications/BambuStudio.app/Contents/Resources/profiles",
    "C:/Program Files/Bambu Studio/resources/profiles",
]


def die(msg: str) -> NoReturn:  # type: ignore[valid-type]
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def find(cands: list[str], env: str, what: str) -> Path:
    override = os.environ.get(env)
    if override:
        p = Path(override).expanduser()
        if p.exists():
            return p
        die(f"{env} does not exist: {p}")
    for c in cands:
        p = Path(c).expanduser()
        if p.exists():
            return p
    die(f"could not find {what}; set {env}")


def resolve_preset(name_or_path: str, kind: str, vendor: str = "BBL") -> Path:
    p = Path(name_or_path).expanduser()
    if p.is_file():
        return p
    root = find(
        PROFILES_CANDIDATES,
        "BAMBU_PROFILES_ROOT",
        "the Bambu Studio profiles directory",
    )
    cand = root / vendor / kind / f"{name_or_path}.json"
    if cand.is_file():
        return cand
    die(f"no {kind} preset named {name_or_path!r} (and no such file)")


# Written to a scratch dir and passed to --load-settings; kept alive for the run.
_FLAT_DIR: Path | None = None


def flatten_preset(path: Path | None, kind: str) -> Path | None:
    """Resolve a preset's inheritance chain into a self-contained file.

    This is not an optimization — it is required for correctness. The CLI does
    NOT follow `inherits`; it applies only the keys literally present in the file
    you hand it. Bambu's shipped presets are deltas, so passing
    `0.12mm Fine @BBL X1C.json` (which contains no `layer_height` at all — that
    lives in its ancestor `fdm_process_single_0.12`) silently slices at the
    default 0.2 mm and reports success.

    That failure is invisible: the gcode is valid, the run exits 0, and the times
    are simply for a print nobody asked for. It is exactly the class of
    confidently-wrong result this script exists to catch, so flattening happens
    unconditionally rather than on request.
    """
    global _FLAT_DIR
    if path is None:
        return None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import bambu_profiles as bp

        index = bp.build_index(bp.find_system_root(), kind)
        cfg = bp.resolve_file(path, index)
    except Exception:
        return path  # better to slice with the delta than to fail outright

    # `inherits` must go, or the CLI looks for a *_full parent it cannot find.
    for key in ("inherits", "instantiation", "setting_id", "from"):
        cfg.pop(key, None)
    cfg["from"] = "User"

    if _FLAT_DIR is None:
        _FLAT_DIR = Path(tempfile.mkdtemp(prefix=".bambu-presets-", dir=Path.home()))
    out = _FLAT_DIR / f"{kind}-{path.stem}.json"
    out.write_text(json.dumps(cfg, indent=2))
    return out


def run_slice(
    model: Path,
    machine: Path | None,
    process: Path | None,
    filament: Path | None,
    outdir: Path,
    project: bool,
    extra: list[str] | None = None,
) -> dict:
    """Invoke the CLI and return its result.json.

    The working directory must live under $HOME: the CLI writes scratch files
    beside the CWD and macOS denies it access under /private/tmp, which surfaces
    as a bare "Unable to open the file ...tmp" rather than a permissions error.
    """
    binary = find(BINARY_CANDIDATES, "BAMBU_BINARY", "the Bambu Studio binary")
    # Clear first: a run that fails leaves the previous run's plate_1.gcode in
    # place, and the next summary would pair a fresh result.json with stale gcode.
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    cmd = [str(binary), "--debug", "2", "--slice", "0", "--outputdir", str(outdir)]
    if not project:
        cmd += ["--arrange", "1"]
    settings = [str(p) for p in (machine, process) if p]
    if settings:
        cmd += ["--load-settings", ";".join(settings)]
    if filament:
        cmd += ["--load-filaments", str(filament)]
    cmd += extra or []
    cmd += [str(model)]

    workdir = Path(tempfile.mkdtemp(prefix=".bambu-slice-", dir=Path.home()))
    try:
        proc = subprocess.run(
            cmd, cwd=workdir, capture_output=True, text=True, timeout=900
        )
    except subprocess.TimeoutExpired:
        die("slicing timed out after 15 minutes")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    rj = outdir / "result.json"
    if not rj.is_file():
        tail = "\n".join((proc.stderr or proc.stdout).splitlines()[-8:])
        die(f"slicer produced no result.json (exit {proc.returncode})\n{tail}")
    result = json.loads(rj.read_text())
    result["_exit"] = proc.returncode
    result["_cmd"] = cmd
    return result


def filament_mass_g(outdir: Path, filament: Path | None) -> float | None:
    """Derive filament mass from extruded length and the preset's density.

    The CLI reports `total_used_g: 0.00` and a `total filament weight [g] : 0.00`
    in the gcode footer — it never resolves density in this mode. Passing that
    zero through would be worse than saying nothing, because "0 g" reads like a
    measurement. Length is reported correctly, and density is in the filament
    preset, so the mass is recoverable.
    """
    gcode = outdir / "plate_1.gcode"
    if not gcode.is_file() or filament is None:
        return None
    length_mm = None
    with gcode.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            if line.startswith("; total filament length [mm]"):
                try:
                    length_mm = float(line.split(":")[1])
                except (IndexError, ValueError):
                    return None
                break
    if not length_mm:
        return None
    cfg = _resolved_filament(filament)
    try:
        density = float(_first(cfg.get("filament_density")))  # g/cm3
        diameter = float(_first(cfg.get("filament_diameter") or "1.75"))
    except (TypeError, ValueError):
        return None
    volume_cm3 = length_mm * 3.14159265 * (diameter / 2) ** 2 / 1000.0
    return round(volume_cm3 * density, 2)


def _resolved_filament(path: Path) -> dict:
    """Density lives up the inheritance chain, not in the leaf preset.

    Bambu's shipped presets are deltas — `Bambu PLA Basic @BBL X1C.json` never
    mentions `filament_density`; its ancestor does. Reading the leaf alone finds
    nothing, so reuse the resolver that already walks the chain.
    """
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        import bambu_profiles as bp

        index = bp.build_index(bp.find_system_root(), "filament")
        return bp.resolve_file(path, index)
    except Exception:
        try:
            return json.loads(path.read_text())
        except (OSError, json.JSONDecodeError):
            return {}


def _first(value):
    """Bambu preset values are per-variant arrays; scalars appear bare."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def summarize(
    result: dict, outdir: Path | None = None, filament: Path | None = None
) -> dict:
    plates = result.get("sliced_plates") or []
    plate = plates[0] if plates else {}
    grams = sum(f.get("total_used_g", 0.0) for f in plate.get("filaments", []))
    if not grams and outdir is not None:
        derived = filament_mass_g(outdir, filament)
        grams = derived if derived is not None else 0.0
    return {
        "ok": result.get("return_code") == 0,
        "error": result.get("error_string", ""),
        "layer_height": round(result.get("layer_height", 0.0), 3),
        "wall_loops": result.get("wall_loops"),
        "sparse_infill_density": result.get("sparse_infill_density"),
        "seconds": round(plate.get("total_predication", 0.0)),
        "grams": round(grams, 2) if grams else None,
        "feature_times": plate.get("feature_type_times", {}),
        "warning": plate.get("warning_message", ""),
        "triangles": plate.get("triangle_count"),
    }


def fmt_hms(seconds: float) -> str:
    s = int(seconds)
    return (
        f"{s // 3600}h{(s % 3600) // 60:02d}m"
        if s >= 3600
        else f"{s // 60}m{s % 60:02d}s"
    )


def print_summary(label: str, s: dict) -> None:
    print(f"\n=== {label} ===")
    if not s["ok"]:
        print(f"  FAILED: {s['error']}")
        return
    print(
        f"  applied : layer {s['layer_height']} mm · {s['wall_loops']} walls · {s['sparse_infill_density']}% infill"
    )
    mass = f" · {s['grams']} g" if s["grams"] else " · mass unavailable"
    print(f"  estimate: {fmt_hms(s['seconds'])}{mass}")
    if s["feature_times"]:
        top = sorted(s["feature_times"].items(), key=lambda kv: -kv[1])[:6]
        print("  time by feature:")
        for name, secs in top:
            print(
                f"    {name:<24} {fmt_hms(secs):>8}  ({100 * secs / s['seconds']:.0f}%)"
            )
    if s["warning"]:
        print(f"  slicer warning: {s['warning']}")


def _presets(args) -> tuple[Path | None, Path | None, Path | None]:
    # Only the process preset is flattened. Machine presets carry `include`
    # directives pointing at gcode templates resolved relative to the original
    # file, so a copy in a temp dir loses them and the printer reads as
    # incompatible. Machine deltas apply correctly as-is.
    machine = resolve_preset(args.machine, "machine") if args.machine else None
    filament = resolve_preset(args.filament, "filament") if args.filament else None
    process = (
        flatten_preset(resolve_preset(args.process, "process"), "process")
        if getattr(args, "process", None)
        else None
    )
    return machine, process, filament


def cmd_check(args) -> None:
    model = Path(args.model).expanduser()
    if not model.is_file():
        die(f"no such model: {model}")
    machine, process, filament = _presets(args)
    out = (
        Path(args.outdir).expanduser()
        if args.outdir
        else Path.home() / ".cache/bambu-slice/check"
    )
    result = run_slice(
        model, machine, process, filament, out, project=model.suffix.lower() == ".3mf"
    )
    s = summarize(result, out, filament)
    print_summary(f"{model.name} · {args.process or 'preset from project'}", s)
    if not s["ok"]:
        _explain_failure(s, machine)
        sys.exit(1)
    print(f"\n  gcode: {out}/plate_1.gcode")


def cmd_compare(args) -> None:
    model = Path(args.model).expanduser()
    if not model.is_file():
        die(f"no such model: {model}")
    machine, _, filament = _presets(args)
    base_src, cand_src = (
        resolve_preset(args.base, "process"),
        resolve_preset(args.candidate, "process"),
    )
    base = flatten_preset(base_src, "process")
    cand = flatten_preset(cand_src, "process")
    root = (
        Path(args.outdir).expanduser()
        if args.outdir
        else Path.home() / ".cache/bambu-slice/compare"
    )

    is_project = model.suffix.lower() == ".3mf"
    rb = summarize(
        run_slice(model, machine, base, filament, root / "base", is_project),
        root / "base",
        filament,
    )
    rc = summarize(
        run_slice(model, machine, cand, filament, root / "candidate", is_project),
        root / "candidate",
        filament,
    )

    print_summary(f"BASE · {base_src.stem}", rb)
    print_summary(f"CANDIDATE · {cand_src.stem}", rc)

    if not (rb["ok"] and rc["ok"]):
        _explain_failure(rb if not rb["ok"] else rc, machine)
        sys.exit(1)

    dt = rc["seconds"] - rb["seconds"]
    dg = (rc["grams"] or 0) - (rb["grams"] or 0)
    print("\n=== delta (candidate - base) ===")
    print(
        f"  time : {'+' if dt >= 0 else '-'}{fmt_hms(abs(dt))}"
        f"  ({100 * dt / rb['seconds']:+.0f}%)"
        if rb["seconds"]
        else ""
    )
    if rb["grams"] and rc["grams"]:
        print(f"  mass : {dg:+.2f} g  ({100 * dg / rb['grams']:+.0f}%)")
    keys = set(rb["feature_times"]) | set(rc["feature_times"])
    moved = sorted(
        (
            (k, rc["feature_times"].get(k, 0) - rb["feature_times"].get(k, 0))
            for k in keys
        ),
        key=lambda kv: -abs(kv[1]),
    )[:6]
    print("  biggest shifts by feature:")
    for name, d in moved:
        if abs(d) >= 1:
            print(f"    {name:<24} {d:+8.0f} s")


def _explain_failure(s: dict, machine: Path | None) -> None:
    if "multi-extruder" not in (s.get("error") or ""):
        return
    name = machine.stem if machine else "this printer"
    print(
        f"\n  {name} is a multi-extruder machine, and the CLI has no flag to map\n"
        "  filaments to nozzles. Either pass a 3MF exported from Bambu Studio (the\n"
        "  GUI bakes the mapping in), or compare against a single-extruder printer\n"
        "  as a proxy and report the delta as relative, not absolute.",
        file=sys.stderr,
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument(
            "model",
            help=".stl or .3mf (a Studio-exported .3mf carries its own presets)",
        )
        p.add_argument(
            "--machine",
            help="machine preset name or path, e.g. 'Bambu Lab X1 Carbon 0.4 nozzle'",
        )
        p.add_argument("--filament", help="filament preset name or path")
        p.add_argument("--outdir", help="where to write gcode + result.json")
        return p

    p = common(sub.add_parser("check"))
    p.add_argument("--process", help="process preset name or path")

    p = common(sub.add_parser("compare"))
    p.add_argument("--base", required=True, help="process preset to measure against")
    p.add_argument("--candidate", required=True, help="process preset being proposed")

    args = ap.parse_args()
    {"check": cmd_check, "compare": cmd_compare}[args.cmd](args)


if __name__ == "__main__":
    try:
        main()
    finally:
        if _FLAT_DIR is not None:
            shutil.rmtree(_FLAT_DIR, ignore_errors=True)
