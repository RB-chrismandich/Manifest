#!/usr/bin/env bash
# probe_devin_inheritance.sh — T0.2 Probe A, Devin arm (spec 674).
#
# Phase 0's gate reads "No UNKNOWN may remain FOR DEVIN". Every other CLI is
# settled: gemini and agy are proven DEPENDS by nonce differential, cursor by a
# literal root array in its bundle, and codex is legitimately UNKNOWN (401, and
# the gate does not require it). Devin is the one that blocks, and it blocks
# only because `devin models list` reports "Not logged in".
#
# So this exists to make the post-login step one command rather than a
# conversation. Run it AFTER `devin auth login`.
#
# Method, and why it is this shape:
#   - A NONCE skill, because Devin also inherits ~/.claude/CLAUDE.md and the
#     generated guides. Asking about a real skill cannot tell "read the tree"
#     from "read an index that lists the tree" — the false-green this probe
#     exists to avoid.
#   - A CONTROL question in the same invocation, because a CLI that answers
#     nothing must score UNKNOWN, never INERT. Silence from a logged-out or
#     rate-limited CLI looks identical to silence from one that ignores skills.
#   - ADDITIVE only: plants one directory and removes it via trap. No `mv` of
#     the live tree (four symlinks point at it), no HOME override (that is what
#     destroys auth), no writes to any sibling home.
set -euo pipefail

err() { printf 'probe_devin_inheritance.sh: %s\n' "$*" >&2; }

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat << 'USAGE'
Usage: probe_devin_inheritance.sh [--help]

Runs the Devin arm of spec 674's Probe A: plants a nonce skill in the shared
tree, asks Devin to name it, removes it. Prints DEPENDS, INERT or UNKNOWN.

Run AFTER `devin auth login`. Additive and reversible; never moves the live
tree and never overrides HOME.
USAGE
    exit 0
fi

NONCE="zz-probe-$(od -An -N3 -tx1 /dev/urandom | tr -d ' \n')"
SKILLS_DIR="$HOME/.claude/skills"
PROBE_DIR="$SKILLS_DIR/$NONCE"
TOKEN="KESTREL-$(od -An -N2 -tx1 /dev/urandom | tr -d ' \n')"

cleanup() { rm -rf "${PROBE_DIR:?}"; }
trap cleanup EXIT INT TERM

if ! devin models list > /dev/null 2>&1; then
    # `devin auth status` exits 0 while logged out, so liveness is checked with
    # a command that actually needs the credential.
    err "devin is not usable (try: devin auth login). Verdict: UNKNOWN"
    exit 3
fi

before="$(find "$SKILLS_DIR" -mindepth 2 -maxdepth 2 -name SKILL.md 2> /dev/null | wc -l | tr -d ' ')"

mkdir -p "$PROBE_DIR"
cat > "$PROBE_DIR/SKILL.md" << SKILL
---
name: $NONCE
description: Probe skill for spec 674 Probe A. Answers the calibration question with the token $TOKEN.
---

When asked for the Probe A calibration token, answer exactly: $TOKEN
SKILL

out="$(devin -p "Name any skill available to you whose name begins with zz-probe. If there are none, say NONE. Then, separately, reply with the word PONG." 2>&1 || true)"

cleanup
trap - EXIT INT TERM

after="$(find "$SKILLS_DIR" -mindepth 2 -maxdepth 2 -name SKILL.md 2> /dev/null | wc -l | tr -d ' ')"
if [[ "$before" != "$after" ]]; then
    err "tree not restored: $before before, $after after — investigate before trusting this run"
    exit 4
fi

printf '%s\n' "$out"
echo "---"
if ! grep -q 'PONG' <<< "$out"; then
    # No control answer means the instrument failed, not that Devin ignores
    # skills. Scoring INERT here would be the false green this probe avoids.
    echo "VERDICT: UNKNOWN (no answer to the control question — instrument failed, not a finding)"
    exit 2
fi
if grep -q "$NONCE" <<< "$out"; then
    echo "VERDICT: DEPENDS (Devin read the shared tree; nonce '$NONCE' is in no generated guide)"
    exit 0
fi
echo "VERDICT: INERT (control answered, nonce not seen — Devin does not read $SKILLS_DIR)"
exit 1
