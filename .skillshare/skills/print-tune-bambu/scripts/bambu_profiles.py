#!/usr/bin/env python3
"""Read Bambu Studio's own profile database so print-setting advice is anchored
on the real stock values and the real config key names, not on recollection.

Bambu Studio ships every system preset as JSON under its Resources directory.
Each preset declares `inherits`, forming a chain that ends at a common base.
The value a slider actually shows is the deepest override in that chain, so any
honest "change X from A to B" claim requires resolving the chain first.

Commands
    root                       Show detected system + user preset directories
    list                       List base presets (filter by printer/nozzle/kind)
    resolve NAME               Print the fully resolved config for a preset
    get NAME KEY [KEY...]      Print resolved values for specific keys
    trace NAME KEY             Show which file in the chain last set KEY
    user-list                  List the user's own saved presets
    validate FILE              Check a candidate user preset before handing it over
    install FILE --yes         Copy a validated preset into the user preset dir

Set BAMBU_PROFILES_ROOT / BAMBU_USER_ROOT to override path detection.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import NoReturn

SYSTEM_CANDIDATES = [
    "/Applications/BambuStudio.app/Contents/Resources/profiles",
    "C:/Program Files/Bambu Studio/resources/profiles",
    "C:/Program Files (x86)/Bambu Studio/resources/profiles",
    "~/.local/share/BambuStudio/profiles",
    "/usr/share/bambu-studio/profiles",
]

USER_CANDIDATES = [
    "~/Library/Application Support/BambuStudio/user",
    "~/AppData/Roaming/BambuStudio/user",
    "~/.config/BambuStudio/user",
]

# Keys that hold one value per extruder variant on multi-extruder machines.
# Length must match the machine's print_extruder_variant list or the preset is
# silently misapplied, which is the single easiest way to ship a broken profile.
PER_VARIANT_SENTINEL = "print_extruder_variant"


def die(msg: str) -> NoReturn:  # type: ignore[valid-type]
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def find_system_root() -> Path:
    env = os.environ.get("BAMBU_PROFILES_ROOT")
    if env:
        p = Path(env).expanduser()
        if p.is_dir():
            return p
        die(f"BAMBU_PROFILES_ROOT does not exist: {p}")
    for c in SYSTEM_CANDIDATES:
        p = Path(c).expanduser()
        if p.is_dir():
            return p
    die(
        "could not find Bambu Studio's profiles directory. Install Bambu Studio "
        "or set BAMBU_PROFILES_ROOT to the directory containing BBL/."
    )


def find_user_root() -> Path | None:
    env = os.environ.get("BAMBU_USER_ROOT")
    if env:
        p = Path(env).expanduser()
        return p if p.is_dir() else None
    for c in USER_CANDIDATES:
        p = Path(c).expanduser()
        if p.is_dir():
            return p
    return None


def user_preset_dir(kind: str = "process") -> Path | None:
    """Pick the logged-in account's preset dir over `default`, since that is the
    one Bambu Studio actually shows in the preset dropdown for a signed-in user."""
    root = find_user_root()
    if root is None:
        return None
    accounts = [d for d in sorted(root.iterdir()) if d.is_dir()]
    numeric = [d for d in accounts if d.name.isdigit()]
    for d in numeric + accounts:
        sub = d / kind
        if sub.is_dir():
            return sub
    return None


def build_index(root: Path, kind: str, vendor: str = "BBL") -> dict[str, Path]:
    """Map preset name -> file, scoped to one vendor.

    Scoping matters: every vendor ships its own `fdm_process_common`, so a
    cross-vendor index would happily resolve a Bambu preset's base against
    Anker's file and report stock values that the user's slicer never shows.
    """
    d = root / vendor / kind
    if not d.is_dir():
        available = sorted(p.name for p in root.iterdir() if (p / kind).is_dir())
        die(
            f"no {kind} presets for vendor {vendor!r}. Available: {', '.join(available)}"
        )
    return {f.stem: f for f in sorted(d.rglob("*.json"))}


BINARY_CANDIDATES = [
    "/Applications/BambuStudio.app/Contents/MacOS/BambuStudio",
    "C:/Program Files/Bambu Studio/bambu-studio.exe",
    "/usr/bin/bambu-studio",
    "/usr/local/bin/bambu-studio",
]

_KEY_RE = re.compile(rb"[a-z][a-z0-9_]{5,45}")
# C++ symbol fragments in the binary look like `lic3r22detect_overhang_degree`:
# a mangled length prefix welded onto the name. Real config keys only carry
# digits as underscore-delimited tokens (`overhang_1_4_speed`), so a digit sitting
# directly after a letter is a reliable tell that the string is symbol debris.
_MANGLED = re.compile(r"[a-z]\d")
_DIGIT_TOKEN = re.compile(r"_\d")


def _plausible_key(s: str) -> bool:
    return not _MANGLED.search(s) or bool(_DIGIT_TOKEN.search(s))


def known_keys() -> set[str] | None:
    """Every config key Bambu Studio understands, harvested from its binary.

    The shipped presets only contain keys they *override*, so a key like
    `support_remove_small_overhang` is absent from all of them even though the
    checkbox exists. Validating against the preset files alone would therefore
    reject perfectly good settings. The binary embeds the full option table, so
    it is the only complete source available offline.

    Returns None if the binary cannot be found, so callers can degrade to the
    weaker preset-derived check rather than block.
    """
    env = os.environ.get("BAMBU_BINARY")
    paths = (
        [Path(env).expanduser()]
        if env
        else [Path(c).expanduser() for c in BINARY_CANDIDATES]
    )
    for p in paths:
        if not p.is_file():
            continue
        try:
            blob = p.read_bytes()
        except OSError:
            continue
        return {
            s for m in _KEY_RE.findall(blob) if _plausible_key(s := m.decode("ascii"))
        }
    return None


def load_json(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        die(f"{path} is not valid JSON: {exc}")


def chain(
    name: str, index: dict[str, Path], _seen: set[str] | None = None
) -> list[tuple[str, Path, dict]]:
    """Return [(name, path, raw), ...] from the requested preset up to the root base."""
    _seen = _seen or set()
    if name in _seen:
        die(f"circular inherits at {name!r}")
    _seen.add(name)
    path = index.get(name)
    if path is None:
        die(f"no preset named {name!r}. Try: bambu_profiles.py list --kind process")
    raw = load_json(path)
    out = [(name, path, raw)]
    parent = raw.get("inherits")
    if parent:
        out.extend(chain(parent, index, _seen))
    return out


def resolve(name: str, index: dict[str, Path]) -> dict:
    merged: dict = {}
    for _, _, raw in reversed(chain(name, index)):  # base first, child last wins
        merged.update(raw)
    return merged


def resolve_file(path: Path, index: dict[str, Path]) -> dict:
    """Resolve a preset that lives outside the index (e.g. a user export)."""
    raw = load_json(path)
    parent = raw.get("inherits")
    merged = resolve(parent, index) if parent else {}
    merged.update(raw)
    return merged


# ---------------------------------------------------------------------------
# commands


def cmd_root(args, sysroot: Path) -> None:
    print(f"system profiles: {sysroot}")
    for kind in ("process", "filament", "machine"):
        d = user_preset_dir(kind)
        print(f"user {kind:<8}: {d if d else '(not found)'}")


def cmd_list(args, sysroot: Path) -> None:
    index = build_index(sysroot, args.kind, args.vendor)
    names = sorted(index)
    if args.printer:
        names = [n for n in names if re.search(args.printer, n, re.I)]
    if args.nozzle:
        # "@BBL H2D" with no nozzle suffix means the machine's default 0.4.
        if args.nozzle in ("0.4", "0.4mm"):
            names = [n for n in names if not re.search(r"0\.[268] nozzle", n)]
        else:
            noz = args.nozzle.replace("mm", "")
            names = [n for n in names if f"{noz} nozzle" in n]
    if not args.include_abstract:
        names = [n for n in names if not n.startswith("fdm_")]
    for n in names:
        print(n)


def cmd_resolve(args, sysroot: Path) -> None:
    index = build_index(sysroot, args.kind, args.vendor)
    src = Path(args.name)
    cfg = resolve_file(src, index) if src.is_file() else resolve(args.name, index)
    print(json.dumps(cfg, indent=2, sort_keys=True))


def cmd_get(args, sysroot: Path) -> None:
    index = build_index(sysroot, args.kind, args.vendor)
    src = Path(args.name)
    cfg = resolve_file(src, index) if src.is_file() else resolve(args.name, index)
    missing = []
    for key in args.keys:
        if key in cfg:
            print(f"{key} = {json.dumps(cfg[key])}")
        else:
            missing.append(key)
    for key in missing:
        print(f"{key} = <NOT SET IN THIS CHAIN>")
    if missing:
        sys.exit(2)


def cmd_trace(args, sysroot: Path) -> None:
    index = build_index(sysroot, args.kind, args.vendor)
    for name, path, raw in chain(args.name, index):
        if args.key in raw:
            print(f"{name}\n  file : {path}\n  value: {json.dumps(raw[args.key])}")
            return
    print(f"{args.key} is not set anywhere in the inheritance chain of {args.name!r}")
    sys.exit(2)


def cmd_user_list(args, sysroot: Path) -> None:
    d = user_preset_dir(args.kind)
    if d is None:
        die("could not locate the Bambu Studio user preset directory")
    files = sorted(d.glob("*.json"))
    if not files:
        print(f"(no saved {args.kind} presets in {d})")
        return
    for f in files:
        raw = load_json(f)
        print(f"{f.stem}\n  inherits: {raw.get('inherits', '(none)')}\n  file    : {f}")


def _variant_len(cfg: dict) -> int | None:
    v = cfg.get(PER_VARIANT_SENTINEL)
    return len(v) if isinstance(v, list) else None


def cmd_keys(args, sysroot: Path) -> None:
    """Search the full config vocabulary, not just what the presets happen to set."""
    index = build_index(sysroot, args.kind, args.vendor)
    overridden: set[str] = set()
    for f in index.values():
        overridden |= set(load_json(f))
    # Keys in the user's own exports are proven real too — Bambu Studio wrote
    # them — and they cover options no stock preset happens to change.
    udir = user_preset_dir(args.kind)
    if udir:
        for f in udir.glob("*.json"):
            overridden |= set(load_json(f))
    vocabulary = known_keys()
    if vocabulary is None:
        print(
            "note: Bambu Studio binary not found; showing only keys some preset overrides",
            file=sys.stderr,
        )
        vocabulary = overridden

    pat = re.compile(args.pattern, re.I) if args.pattern else None
    hits = sorted(k for k in vocabulary if pat is None or pat.search(k))
    if not hits:
        print(f"no config key matches {args.pattern!r}")
        sys.exit(2)
    # A key some preset sets is proven real. The rest come from the binary's
    # symbol table, which also holds internal names that are not user settings —
    # so they are leads to confirm in the UI, not facts to quote.
    for k in hits:
        print(f"{'CONFIRMED' if k in overridden else 'candidate'}  {k}")


def cmd_validate(args, sysroot: Path) -> None:
    path = Path(args.file).expanduser()
    if not path.is_file():
        die(f"no such file: {path}")
    raw = load_json(path)
    index = build_index(sysroot, args.kind, args.vendor)

    errors: list[str] = []
    warnings: list[str] = []

    for required in ("name", "inherits", "from"):
        if required not in raw:
            errors.append(f"missing required field {required!r}")
    if raw.get("from") != "User":
        errors.append(
            f"'from' must be \"User\" for an importable preset, got {raw.get('from')!r}"
        )
    if raw.get("name") and raw.get("print_settings_id") not in (None, raw["name"]):
        warnings.append(
            "print_settings_id differs from name; Bambu Studio normally keeps them identical"
        )

    parent = raw.get("inherits")
    base = {}
    if parent:
        if parent not in index:
            errors.append(
                f"inherits {parent!r}, which is not a preset in this Bambu Studio install"
            )
        else:
            base = resolve(parent, index)

    in_chain = set(base)
    vocabulary = known_keys()
    expected_len = _variant_len(base)

    for key, val in raw.items():
        if key in (
            "name",
            "inherits",
            "from",
            "print_settings_id",
            "filament_settings_id",
            "version",
            "type",
        ):
            continue
        if vocabulary is not None and key not in vocabulary:
            errors.append(
                f"{key!r} is not a config key Bambu Studio recognizes — it would be ignored on import"
            )
        elif in_chain and key not in in_chain:
            # Legal but worth surfacing: the key is real, just never overridden by
            # any stock preset, so there is no stock value to compare against.
            warnings.append(
                f"{key!r} is a real key but no stock preset sets it; it has no visible 'stock value'"
            )
        if (
            isinstance(val, list)
            and expected_len
            and key.endswith(
                ("_speed", "_acceleration", "_id", "_variant", "_threshold")
            )
            and len(val) != expected_len
        ):
            errors.append(
                f"{key!r} has {len(val)} entries but this machine has {expected_len} extruder variants; "
                f'per-variant arrays must be exactly {expected_len} long (use "nil" to inherit an entry)'
            )
        if (
            isinstance(val, list)
            and expected_len
            and len(val) == expected_len
            and all(v == "nil" for v in val)
        ):
            warnings.append(
                f'{key!r} is all "nil" — it overrides nothing and can be dropped'
            )

    # A per-variant override that only fills slot 0 leaves the second nozzle and
    # the high-flow variants on stock values, which is usually not what was meant.
    if expected_len:
        for key, val in raw.items():
            if (
                isinstance(val, list)
                and len(val) == expected_len
                and val[0] != "nil"
                and all(v == "nil" for v in val[1:])
            ):
                warnings.append(
                    f"{key!r} only overrides variant 0 (left nozzle, Direct Drive Standard); "
                    "the other variants stay at stock. Confirm that is intended."
                )

    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    if errors:
        print(
            f"\n{len(errors)} error(s), {len(warnings)} warning(s) — not safe to import"
        )
        sys.exit(1)
    print(
        f"\nOK — 0 errors, {len(warnings)} warning(s). {len(raw)} keys, inherits {parent!r}"
    )


def cmd_install(args, sysroot: Path) -> None:
    path = Path(args.file).expanduser()
    if not path.is_file():
        die(f"no such file: {path}")
    dest_dir = user_preset_dir(args.kind)
    if dest_dir is None:
        die("could not locate the Bambu Studio user preset directory")
    raw = load_json(path)
    dest = dest_dir / f"{raw.get('name', path.stem)}.json"
    if dest.exists() and not args.force:
        die(f"{dest} already exists; pass --force to overwrite")
    if not args.yes:
        die(f"would write {dest} — re-run with --yes to actually write it")
    shutil.copyfile(path, dest)
    print(f"wrote {dest}")
    print(
        "Restart Bambu Studio (or switch printers and back) for it to appear in the preset list."
    )


def main() -> None:
    # --kind/--vendor are accepted both before and after the subcommand, because
    # both orderings read naturally and guessing wrong is pure friction. The
    # sub-level copies suppress their defaults so they only win when given.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--kind", choices=["process", "filament", "machine"], default=argparse.SUPPRESS
    )
    common.add_argument("--vendor", default=argparse.SUPPRESS)

    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--kind", default="process", choices=["process", "filament", "machine"]
    )
    ap.add_argument(
        "--vendor", default="BBL", help="profile vendor directory (default BBL)"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("root", parents=[common])

    p = sub.add_parser("list", parents=[common])
    p.add_argument("--printer", help="substring/regex, e.g. H2D")
    p.add_argument("--nozzle", help="0.2 | 0.4 | 0.6 | 0.8")
    p.add_argument(
        "--include-abstract", action="store_true", help="also show fdm_* internal bases"
    )

    p = sub.add_parser("resolve", parents=[common])
    p.add_argument("name", help="preset name, or a path to a .json preset file")

    p = sub.add_parser("get", parents=[common])
    p.add_argument("name")
    p.add_argument("keys", nargs="+")

    p = sub.add_parser("trace", parents=[common])
    p.add_argument("name")
    p.add_argument("key")

    p = sub.add_parser("keys", parents=[common])
    p.add_argument(
        "pattern",
        nargs="?",
        help="regex to filter config key names, e.g. 'support.*overhang'",
    )

    sub.add_parser("user-list", parents=[common])

    p = sub.add_parser("validate", parents=[common])
    p.add_argument("file")

    p = sub.add_parser("install", parents=[common])
    p.add_argument("file")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--force", action="store_true")

    args = ap.parse_args()
    sysroot = find_system_root()
    {
        "root": cmd_root,
        "list": cmd_list,
        "resolve": cmd_resolve,
        "get": cmd_get,
        "trace": cmd_trace,
        "keys": cmd_keys,
        "user-list": cmd_user_list,
        "validate": cmd_validate,
        "install": cmd_install,
    }[args.cmd](args, sysroot)


if __name__ == "__main__":
    main()
