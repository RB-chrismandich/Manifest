#!/usr/bin/env bash
# generate_skill_mirror.sh — materialize plugins/*/skills/* into .apm/skills/
# (T3.3, spec 674).
#
# The source of truth moved to plugins/<bundle>/skills/<name>/ in T3.1. This
# regenerates the flat `.apm/skills/<name>/` view that 87 references across 35
# files still read -- tests, command_catalog.py, generate_cursor_rules.sh,
# reconcile_core.py, CI, pre-commit, and the `configs/claude/skills` symlink.
#
# WHY THE MIRROR LANDS AT .apm/skills RATHER THAN dist/skills
#
# The task proposed a new gitignored dist/ path plus retargeting every consumer.
# Measured first: of 87 references, ZERO write the real .apm/skills -- all ten
# apparent writers are test sandboxes rooted at $MANIFEST_ROOT/$STAGE/$PROJ/
# $CLONE/$SCRIPT_DIR. They are reads. Materializing at the SAME path therefore
# collapses that retarget to nothing, and a retarget that never happens cannot
# be done half-way.
#
# REAL FILES, NEVER SYMLINKS
#
# A committed-symlink mirror was rejected on measurement: both copy paths in
# bootstrap/lib/common.sh preserve symlinks-as-symlinks (`rsync -a`, and a
# `cp -R` whose own comment says so), so it would deploy 108 links resolving to
# $HOME/plugins/... -- a path that exists on no machine -- while every repo-side
# gate stayed green, because ci.yml uses `find -L` and the bats fixtures build
# real dirs. `rsync -aL` dereferences, so what lands here is what deploys.
set -euo pipefail

err() { printf 'generate_skill_mirror.sh: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: generate_skill_mirror.sh [--check] [--root DIR] [--help]

Rebuild .apm/skills/ from plugins/*/skills/*. Real files, never symlinks.

  --check   verify the mirror matches the source; exit 1 if stale
  --root    repo root (default: git toplevel, else this script's ancestor)
USAGE
    exit 0
fi

MODE="write"
ROOT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --check) MODE="check" ;;
        --root)
            shift
            ROOT="${1:-}"
            ;;
        *)
            err "unknown argument: $1 (try --help)"
            exit 2
            ;;
    esac
    shift
done

if [[ -z "$ROOT" ]]; then
    ROOT="$(git rev-parse --show-toplevel 2> /dev/null || true)"
fi
[[ -n "$ROOT" ]] || ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"

SRC_GLOB="$ROOT/plugins"
MIRROR="$ROOT/.apm/skills"

if [[ ! -d "$SRC_GLOB" ]]; then
    err "no plugins/ tree at $SRC_GLOB — nothing to mirror"
    exit 2
fi

# Collect source skill dirs. An empty result is an error, never a silent wipe:
# a bad --root that happens to exist would otherwise empty the mirror and every
# downstream gate would then measure an empty tree agreeing with itself.
# `mapfile` is bash 4+; macOS ships bash 3.2 and this repo targets it
# (specs/003 FR-011). read -r in a while loop is the portable form.
SKILL_DIRS=()
while IFS= read -r _d; do
    [[ -n "$_d" ]] && SKILL_DIRS+=("$_d")
done < <(find "$SRC_GLOB" -type d -path '*/skills/*' -mindepth 3 -maxdepth 3 2> /dev/null | sort)
unset _d
if [[ ${#SKILL_DIRS[@]} -eq 0 ]]; then
    err "found no plugins/*/skills/* directories under $SRC_GLOB — refusing to write an empty mirror"
    exit 2
fi

if [[ "$MODE" == "check" ]]; then
    missing=0
    for d in "${SKILL_DIRS[@]}"; do
        name="$(basename "$d")"
        if [[ ! -d "$MIRROR/$name" ]]; then
            err "mirror missing: $name"
            missing=1
        fi
    done
    have="$(find "$MIRROR" -mindepth 1 -maxdepth 1 -type d 2> /dev/null | wc -l | tr -d ' ')"
    if [[ "$have" != "${#SKILL_DIRS[@]}" ]]; then
        err "mirror holds $have skills, source has ${#SKILL_DIRS[@]}"
        missing=1
    fi
    [[ "$missing" -eq 0 ]] && echo "mirror is current (${#SKILL_DIRS[@]} skills)"
    exit "$missing"
fi

# Preserve hand-written / tool-managed files at the mirror ROOT before the
# rebuild. `.apm/skills/README.md` describes the tree and `.metadata.json` is
# apm's provenance registry for externally-sourced skills (ai-hooks-integration,
# the Stitch set). A bare `rm -rf` destroyed both on the first run: they are
# tracked, they are not generated, and nothing else recreates them.
PRESERVE="$(mktemp -d "${TMPDIR:-/tmp}/skill_mirror_keep.XXXXXX")"
if [[ -d "$MIRROR" ]]; then
    find "$MIRROR" -mindepth 1 -maxdepth 1 -type f -exec cp -p {} "$PRESERVE/" \; 2> /dev/null || true
fi

rm -rf "${MIRROR:?}"
mkdir -p "$MIRROR"
for d in "${SKILL_DIRS[@]}"; do
    # -L dereferences: a symlink in the source becomes a real file here, which
    # is the whole point (see the header).
    rsync -aL "$d" "$MIRROR/"
done
# Restore the root files the rebuild cleared.
restored=0
if [[ -d "$PRESERVE" ]]; then
    while IFS= read -r _f; do
        [[ -n "$_f" ]] || continue
        cp -p "$_f" "$MIRROR/"
        restored=$((restored + 1))
    done < <(find "$PRESERVE" -mindepth 1 -maxdepth 1 -type f 2> /dev/null)
    rm -rf "$PRESERVE"
fi
unset _f

# --- qualified -> bare, for the flat-tree consumers -------------------------
#
# The plugin bodies carry QUALIFIED names (`/manifest-docs:docs-all`) because
# that is the only form Claude Code resolves once a skill ships in a bundle.
# The mirror feeds a different world: ~/.manifest/skills is a FLAT tree read by
# cursor, gemini, codex, antigravity and devin, none of which know a bundle
# namespace. Shipping `/manifest-docs:docs-all` there names a command that
# cannot exist on those harnesses.
#
# So the same body is rendered twice from one source, and the mapping is
# mechanical: strip the bundle prefix the registry assigned.
REGISTRY="${MANIFEST_SKILL_REGISTRY:-$ROOT/configs/claude/config/skill_policies.yml}"
if [[ -r "$REGISTRY" ]]; then
    bare_count="$(python3 - "$MIRROR" "$REGISTRY" << 'PY'
import pathlib, re, sys

mirror, registry = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
bundles, cur, seen = set(), None, False
for line in registry.read_text(encoding="utf-8").splitlines():
    stripped = line.split("#", 1)[0].rstrip()
    if stripped.startswith("bundles:"):
        seen = True
        continue
    if not seen:
        continue
    if stripped.startswith("  ") and stripped.endswith(":") and not stripped.startswith("    "):
        cur = stripped.strip()[:-1]
        bundles.add(cur)
    elif stripped and not stripped.startswith(" "):
        seen = False

if not bundles:
    print(0)
    raise SystemExit(0)

pattern = re.compile(r"/(?:" + "|".join(re.escape(b) for b in sorted(bundles, key=len, reverse=True)) + r"):")
changed = 0
for skill_md in sorted(mirror.rglob("*.md")):
    text = skill_md.read_text(encoding="utf-8")
    new = pattern.sub("/", text)
    if new != text:
        skill_md.write_text(new, encoding="utf-8")
        changed += 1
print(changed)
PY
)"
    echo "Rendered bare names in $bare_count mirror file(s)"
fi

echo "Mirrored ${#SKILL_DIRS[@]} skills -> ${MIRROR#"$ROOT"/} (preserved $restored root file(s))"
