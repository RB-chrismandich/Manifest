# Shared Checks — native hook adapters

> `manifest hook <client> <event>`: thin adapters that run `manifest check`
> from a live client's own hook substrate. Split out of
> [SHARED_CHECKS.md](SHARED_CHECKS.md), which is already over its line cap.

## What this is

Four thin, per-client modules — `src/manifest_agent/hooks/{claude_code,codex,
cursor,gemini}.py`, each ≤200 lines — plus shared mechanics in `core.py`,
`state.py`, `receipt.py`, and `runner.py`. Each adapter:

- reads **bounded** stdin (256 KiB cap) and applies one absolute deadline to
  stdin, state-lock acquisition, check execution, telemetry, and receipts;
- parses JSON structurally, with per-client field-type validation (malformed
  input is a protocol response, never a traceback);
- rejects `..` traversal segments in `cwd` and any `tool_input.file_path`
  (string-checked, not resolved — a value can be rejected for containing a
  traversal segment even where `Path.resolve()` would land somewhere safe);
- launches a trusted, isolated `manifest_agent` runtime rather than importing
  `-m manifest_agent` from the project working directory, then invokes
  `manifest check <profile>` via argv only. The check executor caps each body
  to the remaining budget, reserving 250 ms for result serialization. A
  timeout kills the body's process group; post-kill pipe draining is separately
  bounded if a deliberately detached descendant retained a pipe;
- deduplicates repeated events by `(client, event, candidate_digest)` under an
  `fcntl`-locked state file. The lock is held for the full duration of an
  uncached event, including the `manifest check` invocation itself: a
  duplicate that arrives while the first event's verdict is still being
  computed blocks on the same lock rather than answering `allow` for an
  unknown state, and once unblocked replays the exact cached verdict. A
  burst of identical events therefore runs the check exactly once, and every
  member of the burst gets the same decision the first one produced —
  including a `block`, not just a `PASS`. Active Stop continuations never
  re-run a blocked full check. Cached entries are pruned before lookup after
  24h and capped at the newest 500 entries;
- writes a receipt (same `fcntl` lock idiom as `preparation.py`) that always
  carries `"client_version_verified": false`;
- refuses to re-enter when `MANIFEST_HOOK_ACTIVE` is already set. This
  adapter sets it on the `manifest check` child it spawns, and
  `checks/cli.py::_ENVIRONMENT_KEYS` forwards it into every check body's own
  subprocess in turn — so a check body that itself shells out to a client
  CLI (which could re-invoke `manifest hook`) sees the marker too, not just
  the direct child.

State lives under `$XDG_STATE_HOME/manifest/hooks/` (`state.json` for dedup +
stop-continuation, `receipts/` for receipts). Nothing is written to `~/`
outside that directory.

## Event → profile mapping

`quick` covers file-edit / pre-commit-style moments; `full` only the explicit
stop/handoff events; everything else is `{"coverage": "unsupported"}` —
**never emulated**.

| Client | quick | full | unsupported (examples) |
|---|---|---|---|
| `claude-code` | `PreToolUse`, `PostToolUse`, `PostToolUseFailure` | `Stop`, `SubagentStop`, `TaskCompleted` | `SessionStart`, `UserPromptSubmit`, `PermissionRequest`, `Notification`, `SubagentStart`, `TeammateIdle`, `ConfigChange`, `WorktreeCreate`, `WorktreeRemove`, `PreCompact`, `SessionEnd` |
| `cursor` | `beforeShellExecution` | — | every other event name (Cursor's documented hook surface in this repo is `beforeShellExecution` only) |
| `gemini` | `BeforeTool` | — | `SessionStart`, `SessionEnd` (lifecycle-only, no gating semantics) |
| `codex` | — | — | **every** event — see below |

## Codex: no substrate, by construction

`configs/codex/AGENTS.md` states plainly: "Codex and Antigravity have no
event-hook substrate." No Codex hook contract exists anywhere in this
repository. `codex.py`'s `EVENT_PROFILE` is the empty dict; every event
reports `{"coverage": "unsupported"}`. Bounded/structural stdin handling
still applies uniformly (oversized/malformed input still yields a protocol
response, never a traceback), so a client that later grows a real substrate
does not inherit a worse contract than an unsupported one gets today.

## Unsupported-event contract

An event absent from an adapter's `EVENT_PROFILE` table (or present but
mapped to `None`) always produces exactly `{"coverage": "unsupported"}` on
stdout — no check runs, no receipt is written, no other adapter is asked to
cover it. `tests/python/manifest_agent/hooks/test_hooks_fixture_parity.py`
asserts both directions: every vendored fixture event appears in the
adapter's own table, and every event the table claims to support has a
vendored fixture backing that claim.

## Nothing here has been verified against a real client

This is the honesty constraint the chunk was built under, not a hedge:

- The per-client protocol shapes are vendored as
  `tests/fixtures/hooks/<client>/unverified/*.json`, derived from what this
  repository already implements and documents (the
  `ai-hooks-integration` skill's contract/schema files,
  `configs/claude/scripts/constitution_hook.py`). Each client's `SOURCE.md`
  says so explicitly. The directory name is `unverified`, not a version
  number, because no pinned client version was read to produce these shapes.
- No adapter has been run under an actual Fable/Astra/Opus/Sol-mapped client.
  The model/client mapping itself is unresolved (see the phase-3–5 decision
  doc, open question 3).
- Every receipt this adapter writes carries `"client_version_verified":
  false`. This is not a placeholder to fill in later automatically — it is
  the accurate statement of what a receipt from this chunk can attest to.
  Flipping it requires `manifest hook verify <client> --write` to observe a
  successful version probe and a successful protocol probe whose shape exactly
  matches the sole JSON fixture being promoted. A client with multiple event
  fixtures remains `unavailable` until per-event probing exists; unexamined
  fixtures are never promoted client-wide.
- Native protocol semantics are explicit. `TaskCompleted` blocks with exit 2
  and stderr feedback as Claude Code requires; JSON-decision events return
  their client-specific response shapes.

## Related Documents

- [SHARED_CHECKS.md](SHARED_CHECKS.md) — the `manifest check` / `check-aggregate` entry
- [config/project-checks.json](../config/project-checks.json) — the check registry
- `plugins/manifest-workspace/skills/ai-hooks-integration/` — the vendored contract/schema source material
- `tests/fixtures/hooks/` — per-client fixtures, source-labeled `unverified`
- `tests/python/manifest_agent/hooks/` — the fixture harness and negative-fixture suite
