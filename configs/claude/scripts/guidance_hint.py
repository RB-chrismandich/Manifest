#!/usr/bin/env python3
"""Emit one-shot workflow hints at recognized moments (spec 362, US2/US3).

Reads the hint registry (configs/claude/config/hint_registry.yml), maps a
Workflow Moment — detected from a hook payload or passed explicitly — to the
command(s) to surface, de-duplicates and prioritizes them, and prints a single
transient hint. Output is NEVER added to always-loaded context (FR-009).

The runtime path is **fail-open**: on any error, or when nothing is worth
saying, it prints nothing and exits 0, so it can never block the underlying
action. ``validate_registry`` is the strict, raising counterpart used by tests
and CI to keep the registry honest.

CLI:
    guidance_hint.py [--moment <id>]      explicit moment, else read stdin payload
    (stdin) {"tool_name":"Bash","tool_input":{"command":"git commit -m x"}}

Env overrides (tests): GUIDANCE_REGISTRY, plus HOME for rate-limit state (US3).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

PROG = "guidance_hint.py"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_REGISTRY = _REPO_ROOT / "configs" / "claude" / "config" / "hint_registry.yml"
DEFAULT_PREFS = _REPO_ROOT / "configs" / "claude" / "config" / "guidance.yml"
DEFAULT_LOCAL = "~/.claude/config/guidance_local.yml"  # gitignored; lazily created

# Built-in fallback if the shipped guidance.yml is unreadable (fail-open: still gate).
_BUILTIN_PREFS = {
    "enabled": True,
    "categories": {"hints": True, "reminders": True, "discovery": True},
    "verbosity": "normal",
    "rate_limit": {},
}
_VERBOSITY_RANK = {"quiet": 0, "normal": 1, "verbose": 2}
_VALID_OPT_CATEGORIES = {"hints", "reminders", "discovery"}

# Detector for each registry trigger. `context-high` is signal-only (no command
# text), surfaced via the explicit --moment path.
TRIGGER_PATTERNS = {
    "PreToolUse:git-commit": re.compile(r"\bgit\s+commit\b"),
    "PreToolUse:pr-create": re.compile(r"\b(gh\s+pr\s+create|glab\s+mr\s+create)\b"),
    "command-invoke:*-refactor": re.compile(
        r"(^|[\s/])(go|node|python|shell|terraform)-refactor\b"
    ),
    "context-high": None,
}

VALID_CATEGORIES = {"hint", "reminder"}


class RegistryError(Exception):
    """Raised by validate_registry on a dangling ref / unknown moment / etc."""


def err(msg: str) -> None:
    print(f"{PROG}: {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def load_registry(path=None) -> dict:
    path = path or os.environ.get("GUIDANCE_REGISTRY") or DEFAULT_REGISTRY
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    data.setdefault("moments", [])
    data.setdefault("rules", [])
    return data


def validate_registry(registry: dict, catalog_names) -> None:
    moments = registry.get("moments", [])
    for m in moments:
        if "id" not in m or "trigger" not in m:
            raise RegistryError(f"moment is missing 'id' or 'trigger': {m!r}")
        if m["trigger"] not in TRIGGER_PATTERNS:
            raise RegistryError(
                f"moment '{m['id']}': unsupported trigger '{m['trigger']}'"
            )
    moment_ids = {m["id"] for m in moments}
    for r in registry.get("rules", []):
        if "moment_id" not in r:
            raise RegistryError(f"rule is missing 'moment_id': {r!r}")
        if r["moment_id"] not in moment_ids:
            raise RegistryError(f"rule references unknown moment '{r['moment_id']}'")
        for ref in r.get("command_refs", []):
            if ref not in catalog_names:
                raise RegistryError(
                    f"rule for '{r['moment_id']}': command_ref '{ref}' "
                    f"is not in the catalog (dangling ref)"
                )
        category = r.get("category")
        if category not in VALID_CATEGORIES:
            raise RegistryError(
                f"rule for '{r['moment_id']}': invalid category '{category}'"
            )
        if category == "reminder":
            rl = r.get("rate_limit")
            if not rl:
                raise RegistryError(
                    f"reminder rule for '{r['moment_id']}' must declare a rate_limit"
                )
            # Validate parseability too: a typo like '30min' parses to None at
            # runtime, silently disabling the rate limit (reminder spams every
            # event). Guard the CONSUMED contract, not just presence.
            if _parse_duration(rl) is None:
                raise RegistryError(
                    f"reminder rule for '{r['moment_id']}': rate_limit '{rl}' is "
                    f"unparseable (expected like '30m', '2h', '1d')"
                )


# --------------------------------------------------------------------------- #
# Detection + selection
# --------------------------------------------------------------------------- #
def detect_moment(registry: dict, command_text: str | None) -> str | None:
    if not command_text:
        return None
    for m in registry.get("moments", []):
        pattern = TRIGGER_PATTERNS.get(m["trigger"])
        if pattern is not None and pattern.search(command_text):
            return m["id"]
    return None


def select_hints(registry: dict, moment_id: str) -> list:
    """Rules for a moment, deduped by dedup_key (highest priority wins),
    ordered by priority desc then message."""
    matching = [r for r in registry.get("rules", []) if r.get("moment_id") == moment_id]
    best: dict = {}
    for r in matching:
        key = r.get("dedup_key", r.get("message"))
        if key not in best or r.get("priority", 0) > best[key].get("priority", 0):
            best[key] = r
    return sorted(
        best.values(), key=lambda r: (-r.get("priority", 0), r.get("message", ""))
    )


def format_hints(hints: list) -> str:
    return "\n".join(f"→ {h['message']}" for h in hints)


# --------------------------------------------------------------------------- #
# Hook payload
# --------------------------------------------------------------------------- #
def _command_from_payload(raw: str) -> str | None:
    """Best-effort extraction of a shell command from a hook payload.

    Tolerant across tools (Claude Code `tool_input.command`, and the
    `BeforeTool`-style `args.command`/top-level `command` shapes used by Gemini/
    Cursor via ai-hooks-integration). Unknown shapes return None (fail-open).
    """
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    for container_key in ("tool_input", "args", "toolInput", "input"):
        container = payload.get(container_key)
        if isinstance(container, dict) and isinstance(container.get("command"), str):
            return container["command"]
    if isinstance(payload.get("command"), str):
        return payload["command"]
    return None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG, description="Emit a one-shot workflow hint for a recognized moment."
    )
    p.add_argument(
        "--moment",
        default=None,
        help="explicit Workflow Moment id (e.g. pre-commit, high-context)",
    )
    p.add_argument(
        "--disable",
        metavar="CATEGORY",
        default=None,
        help="opt out of hints|reminders|discovery (writes only guidance_local.yml)",
    )
    p.add_argument(
        "--enable",
        metavar="CATEGORY",
        default=None,
        help="re-enable hints|reminders|discovery in guidance_local.yml",
    )
    p.add_argument(
        "--global-off",
        action="store_true",
        dest="global_off",
        help="set enabled:false in guidance_local.yml (kill-switch)",
    )
    p.add_argument(
        "--global-on",
        action="store_true",
        dest="global_on",
        help="set enabled:true in guidance_local.yml",
    )
    return p


def _local_path() -> str:
    return os.environ.get("GUIDANCE_LOCAL") or DEFAULT_LOCAL


def _handle_pref_write(args) -> int | None:
    """Handle the opt-out/opt-in write flags. Returns an exit code if one fired,
    else None. Writes ONLY guidance_local.yml — never the tracked defaults.

    Unlike the runtime emission path, a failed preference write is NOT fail-open:
    a user toggling the kill-switch must learn if the write failed (a swallowed
    error would leave guidance on while the user believes it is off). A failed
    write reports cleanly via err() + exit 2 rather than a raw traceback.
    """
    local = _local_path()
    try:
        if args.global_off or args.global_on:
            set_local_pref(local, "enabled", bool(args.global_on))
            print(f"guidance: enabled={bool(args.global_on)} written to {local}")
            return 0
        for flag, value in ((args.disable, False), (args.enable, True)):
            if flag:
                if flag not in _VALID_OPT_CATEGORIES:
                    err(
                        f"unknown category '{flag}' (expected one of "
                        f"{', '.join(sorted(_VALID_OPT_CATEGORIES))})"
                    )
                    return 2
                set_local_pref(local, f"categories.{flag}", value)
                print(f"guidance: categories.{flag}={value} written to {local}")
                return 0
    except OSError as exc:
        err(f"could not write {local}: {exc}")
        return 2
    return None


# --------------------------------------------------------------------------- #
# Preferences (US3 — two-layer: shipped defaults ← gitignored local override)
# --------------------------------------------------------------------------- #
def _deep_merge(base: dict, override) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _read_yaml(path) -> dict:
    try:
        data = yaml.safe_load(Path(path).expanduser().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def load_preferences(prefs_path=None, local_path=None) -> dict:
    """Effective prefs = shipped defaults ← user-local override (local wins).

    An absent local file means 'all defaults apply' (T027). A missing shipped
    file falls back to the built-in all-enabled defaults (fail-open).
    """
    prefs_path = prefs_path or os.environ.get("GUIDANCE_PREFS") or DEFAULT_PREFS
    local_path = local_path or os.environ.get("GUIDANCE_LOCAL") or DEFAULT_LOCAL
    shipped = _read_yaml(prefs_path) or _BUILTIN_PREFS
    return _deep_merge(_deep_merge(_BUILTIN_PREFS, shipped), _read_yaml(local_path))


def set_local_pref(local_path, dotted_key: str, value) -> None:
    """Write a single override to guidance_local.yml ONLY (never the tracked
    defaults). Lazily creates the file and its parent dir (SC-004)."""
    p = Path(local_path).expanduser()
    data = _read_yaml(p)
    cursor = data
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        cursor = cursor.setdefault(part, {})
    cursor[parts[-1]] = value
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# --------------------------------------------------------------------------- #
# Rate-limit state (machine-local; never committed)
# --------------------------------------------------------------------------- #
def _state_path() -> Path:
    base = os.environ.get("GUIDANCE_STATE_DIR") or "~/.claude/state/guidance"
    return Path(base).expanduser() / "last_fired.json"


def _as_utc(dt: datetime) -> datetime:
    """Coerce a parsed timestamp to tz-aware UTC. A naive value (from older code
    or a hand-edited state file) would otherwise raise TypeError when subtracted
    from the tz-aware `now`, which fail-open would swallow — silently disabling
    the rate limit (reminder fires every event)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def load_last_fired() -> dict:
    try:
        raw = json.loads(_state_path().read_text(encoding="utf-8"))
        return {k: _as_utc(datetime.fromisoformat(v)) for k, v in raw.items()}
    except Exception:
        return {}


def record_fired(moment_id: str, now: datetime) -> None:
    try:
        p = _state_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        cur = {}
        if p.exists():
            cur = json.loads(p.read_text(encoding="utf-8"))
        cur[moment_id] = now.isoformat()
        p.write_text(json.dumps(cur), encoding="utf-8")
    except Exception:
        pass


def _parse_duration(spec) -> timedelta | None:
    if not spec:
        return None
    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", str(spec))
    if not m:
        return None
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return timedelta(seconds=int(m.group(1)) * units[m.group(2)])


# --------------------------------------------------------------------------- #
# Gating (authoritative resolution order — guidance-prefs-schema.md)
# --------------------------------------------------------------------------- #
def apply_gating(
    hints: list, prefs: dict, moment_id: str, last_fired=None, now=None
) -> list:
    if not prefs.get("enabled", True):
        return []
    cats = prefs.get("categories", {})
    vgate = _VERBOSITY_RANK.get(prefs.get("verbosity", "normal"), 1)
    last_fired = last_fired or {}
    rate_overrides = prefs.get("rate_limit", {}) or {}
    out = []
    for r in hints:
        category = r.get("category", "hint")
        cat_key = {"hint": "hints", "reminder": "reminders"}.get(category, category)
        if not cats.get(cat_key, True):
            continue
        if _VERBOSITY_RANK.get(r.get("level", "normal"), 1) > vgate:
            continue
        if category == "reminder":
            window = _parse_duration(
                rate_overrides.get(moment_id) or r.get("rate_limit")
            )
            ts = last_fired.get(moment_id)
            if window and ts is not None and now is not None and (now - ts) < window:
                continue
        out.append(r)
    return out


def _emit_for_moment(registry: dict, moment_id: str) -> int:
    hints = select_hints(registry, moment_id)
    prefs = load_preferences()
    now = datetime.now(UTC)
    surfaced = apply_gating(hints, prefs, moment_id, load_last_fired(), now)
    if surfaced:
        print(format_hints(surfaced))
        if any(h.get("category") == "reminder" for h in surfaced):
            record_fired(moment_id, now)
    return 0


def main(argv=None) -> int:
    # --help precedes any registry/config load (cli-audit-help).
    args = _build_parser().parse_args(argv)
    # Preference writes (opt-out/opt-in) report errors rather than failing open.
    write_rc = _handle_pref_write(args)
    if write_rc is not None:
        return write_rc
    try:
        registry = load_registry()
        if args.moment:
            moment_id = args.moment
        else:
            moment_id = detect_moment(registry, _command_from_payload(sys.stdin.read()))
        if not moment_id:
            return 0
        return _emit_for_moment(registry, moment_id)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
