# spec-review: switch reviewer from Gemini to agy (Antigravity) — Design

> Point the existing `/spec-review` engine at the `agy` (Antigravity) CLI instead
> of `gemini`, so spec/plan/tasks artifacts are reviewed by Antigravity — on
> demand and via the already-deployed save hook. A reviewer swap, not a new
> subsystem.

**Date**: 2026-06-09
**Status**: Approved — implementation plan and change landed (see
`docs/superpowers/plans/2026-06-09-spec-review-agy-reviewer.md`)
**Audience**: Manifest maintainers

---

## Problem

The `/spec-review` system (skill + `spec_review.sh` engine + fail-open PostToolUse
save hook, all shipped and deployed) currently runs its independent review through
the `gemini` CLI via an injectable seam (`SPEC_REVIEW_GEMINI`). The maintainer
wants **Antigravity (`agy`)** to be the model that reviews specs, enforced through
the existing skill + hook.

`agy` (`~/.local/bin/agy`, v1.0.7) was verified to behave exactly like
`gemini -p` / `claude -p`: it reads the piped prompt on stdin, runs headless with
`-p/--print`, returns the response, and exits 0 (authenticated, no permission
hang). So this is a **drop-in reviewer swap**.

## Decision

**Replace `gemini` with `agy` as the single spec reviewer.** The skill, hook,
debounce, detach, lock, fail-open, and output formats are all model-agnostic and
stay exactly as they are. To keep the seam honest, rename it to be reviewer-
agnostic rather than gemini-specific, so a future swap is a one-line change.

## Non-Goals

- No multi-model / cross-model review (single reviewer = agy; "both gemini and
  agy" was considered and declined).
- No new skill, hook, or config file — enforcement already exists.
- No change to discovery, prompt template, debounce, lock, or fail-open behavior.

---

## Change surface

All within the existing spec-review system.

- **`configs/claude/scripts/spec_review.sh`**
  - Rename the seam `SPEC_REVIEW_GEMINI` → `SPEC_REVIEW_CLI`, default `gemini` →
    **`agy`** (`SPEC_REVIEW_CLI="${SPEC_REVIEW_CLI:-agy}"`).
  - Rename `run_gemini` → `run_reviewer`; the body is unchanged:
    `printf '%s' "$prompt" | "$SPEC_REVIEW_CLI" -p "<instruction>"` (verified: agy
    reads stdin, prints, exits 0). The instruction text is already model-agnostic.
  - Update the two call sites (`review()` and `_silent_review_inline()`).

- **`tests/bats/spec_review.bats`**
  - Rename the `_fake_gemini` stub helper → `_fake_reviewer` and every
    `SPEC_REVIEW_GEMINI=` injection → `SPEC_REVIEW_CLI=`. The stub is model-
    agnostic (it just prints a structured finding), so all assertions hold; the
    network-free seam is preserved.
  - Add one test asserting the **default reviewer is `agy`** (e.g. the script,
    with no `SPEC_REVIEW_CLI` set, invokes a stub named `agy` placed on PATH).

- **Docs**
  - `.skillshare/skills/spec-review/SKILL.md` — description "independent model
    (Gemini)" → "independent model (Antigravity / `agy`)".
  - The `/spec-review` rows in `docs/COMMANDS.md`, `CLAUDE.md`, and
    `configs/claude/CLAUDE.md` — replace "Gemini" with "Antigravity (`agy`)".

## Enforcement ("ensure it's followed") — already in place

No new wiring needed:
- The **deployed PostToolUse hook** runs `spec_review.sh --silent` on every
  Write/Edit to spec/plan/tasks — after this swap it reviews via `agy`.
- The **`/spec-review` skill** is the on-demand path.

The change reaches the live environment the usual way: PR → merge → `./bootstrap.sh
--skip-install --skip-auth` redeploy (the engine script + skill + docs).

## Unchanged (model-agnostic)

Content-hash debounce, detached execution, single-flight + stale-lock self-heal,
fail-open, `--format tree|json`, discovery (speckit + superpowers), and the prompt
template.

## Verification items (carried into the plan)

1. **Headless hook mode:** confirm `agy -p` in the **detached, no-TTY** silent
   path doesn't stall on a tool-permission prompt. The review is pure text
   analysis (the artifacts are piped into the prompt), so agy shouldn't invoke
   tools — but a guarded bats/integration check should confirm it returns and the
   fail-open path still holds if it doesn't.
2. **Timeout:** `agy` default `--print-timeout` is 5m; fine for the detached
   silent path (nothing waits on it) and acceptable on demand. No flag needed in
   V1; revisit only if runs hang.

## Testing

- **bats `spec_review.bats`:** all existing tests pass after the rename (seam +
  stub renamed); the new "default reviewer is `agy`" test; fail-open and detached
  behavior unchanged.
- **shellcheck** clean on `spec_review.sh`.
- **grep guard:** no remaining `SPEC_REVIEW_GEMINI` / `run_gemini` / `_fake_gemini`
  references in scripts, tests, or docs.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| `agy` stalls on a permission prompt in headless hook mode | Review prompt is pure text (no tool use); guarded test; fail-open already swallows a non-zero/timeout in silent mode |
| Lingering `gemini` references after rename | grep guard in the test suite + final review |
| Operators expect the old `SPEC_REVIEW_GEMINI` env var | It's an internal test/override seam, not user-facing; documented in the script header comment under the new name |

## Follow-ups (not in V1)

- Configurable reviewer (`gemini | agy | both`) if cross-model review is wanted
  later — the renamed seam makes this a small addition.
- A `--reviewer` flag / `skillclaw.yml`-style config if per-run selection is
  needed.

---

## Related Documents

- [spec-review design](2026-06-08-spec-review-design.md) — the system this swaps the reviewer in
- [docs/SKILLCLAW.md](../../SKILLCLAW.md)
