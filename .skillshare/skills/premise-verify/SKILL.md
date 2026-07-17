---
name: premise-verify
description: Verify a load-bearing assumption before building on it. Use when a spec, skill, hook, parser, or config depends on an assumed CLI subcommand/flag, tool capability, env var, API response field/date semantics, or container image runtime contract.
---

# Verify the Premise Before Building On It

Designs anchored to unverified assumptions fail the same way every time: a
command that doesn't exist, a flag that is silently ignored, an API field that
isn't there, an env var the image never reads. Verify the load-bearing premise
FIRST — never encode into a spec, parser, or config something you haven't
confirmed runs and behaves as believed.

## Shared verification core

1. **State the premise explicitly and treat it as unverified.** When tempted to
   build on a related-thing-works analogy ("`X_PORT` works, so `X_*` must map
   too"; "the sibling flag exists, so this one must"), STOP — analogy is the
   trap.
2. **Probe it cheaply against the source of truth, not docs or assumption.**
   Run the actual binary, `curl` the actual endpoint, dump the actual
   entrypoint, read the upstream source. (Where docs and source disagree, the
   source of truth wins — docs are a fallback, not proof.)
3. **Grep the source of truth for the exact name** of the flag/var/field/
   subcommand you intend to use. If it is not referenced, it is silently
   ignored — your change does nothing.
4. **If the premise is false, stop and redesign — say so explicitly.** Do not
   silently encode a command/field/setting that can't work. Surface the gap,
   propose the realistic alternative (existing tool, repo-native skill, thin
   wrapper, documented mechanism), and get agreement before designing. Hold the
   line under repeated pushback: restate the factual wall and the alternative
   that serves the real goal.
5. **Validate the change took effect on the live target**, not merely that the
   deploy/command exited 0 — grep the rendered config, hit the endpoint and
   inspect the response, run end-to-end on a real item with known data.
6. **Record the verified facts as evidence** (exact path, version, schema,
   stdin behavior, auth state) in the spec/plan so it cites reality, not assumption, and can't
   silently drift. Commit only after behavior is confirmed, so history
   reflects verified facts rather than guesses.
7. **Re-verify after environment changes.** A premise true last week (agent
   running, socket bound, access tier) may be false now — re-probe before
   recommending a path that depends on it.

## CLI / binary

Use when wrapping, integrating with, or designing around a named CLI/binary,
flag, or env var.

1. **Confirm the binary exists, and try spelling variants** (`agi` vs `agy`,
   hyphen vs underscore) — don't conclude "no such tool" from one name:

   ```bash
   for b in agy agi antigravity ag tool-cli; do
     p=$(command -v "$b" 2>/dev/null) && echo "found: $b -> $p ($("$b" --version 2>&1 | head -1))"
   done
   ```

   Also check common install dirs (`~/.local/bin`, Homebrew, `/usr/local/bin`)
   and whether an installed app ships a CLI.
2. **Distinguish the binary from the IDE/app.** A symlink-only config dir means
   the tool inherits config but provides no CLI. Confirm whether the thing is a
   binary, a daemon, or just an IDE before promising it can do work.
3. **Read its actual subcommands/flags** (`<tool> --help`, plus the relevant
   `<tool> <subcommand> --help`). Do NOT assume a `review`/`run` subcommand
   exists from the tool's name — many "agent" CLIs are just headless
   `-p/--print` prompt runners with no domain subcommands. Confirm it reads
   input the way you assume (argv vs stdin).
4. **Smoke-test headless behavior** before wiring it into automation. Confirm
   it reads the prompt from **stdin**, prints a clean result, exits 0, is
   authenticated, and does **not** hang on a TTY/permission prompt. Bound it:

   ```bash
   echo "Reply with exactly: OK" | timeout 60 <tool> -p 2>&1; echo "exit=$?"
   ```

   (macOS lacks `timeout`; use a background PID + watchdog `kill`.)
5. **If absent, do not encode it into a spec.** Propose the repo-native
   alternative (skill + reusable engine script) instead of inventing a binary —
   and design the engine front-end-agnostic so a future real binary can wrap it
   in a few lines for free.
6. **For an assumed flag or env var**, a working sibling option does NOT imply
   a generic mapping — verify it is consumed (core steps 2–3) before adding it;
   for settings consumed inside a container, see "Image runtime contract".

## API schema

Use after building parsers/clients against assumed or probed response shapes,
and before any analysis depends on the data.

1. **Probe each endpoint live the moment access changes** (e.g. a tier upgrade
   unlocks new datasets). Don't assume the path you coded exists: `curl` it and
   check the HTTP status. A 404 means the path is wrong (often per-ticker
   `/historical/x/{id}` doesn't exist and the real access is an all-item
   `/live/x?id=...`).
2. **Dump the actual keys**, not just the status:
   `python3 -c "import json; d=json.load(open(f)); print(list(d[0].keys()))"`.
   Compare field-by-field against what the parser reads. Assumed fields
   (`Value`) often don't exist; the real value is derived
   (`Shares × PricePerShare`).
3. **Pin down the point-in-time date field explicitly.** Many records carry
   both a *transaction* date and a *disclosure/filing* date. Key on the date
   the info became **public** (`fileDate`/`ReportDate`/`Filed`), never the
   transaction date — disclosure lags days to weeks, and using the wrong one
   fabricates predictive signal (look-ahead bias).
4. **Cross-check against the vendor's official client source** — clone it or
   fetch the specific file and decode it — to confirm exact URLs, auth header
   format, and whether it does any rate-limiting — its absence tells you the
   API is lenient. **github-only**: if the vendor hosts on GitHub, `gh api
   repos/<org>/<client>/contents/<file>` (base64-encoded content, needs
   decoding) is a quick one-shot fetch without cloning; on GitLab use `glab
   api projects/<id>/repository/files/<file>?ref=<branch>` instead, and for
   any other host just `curl`/clone the raw file.
5. **Fix the parser test-first**: update the fixture to the *verified* real
   shape (including the two distinct date fields), assert the correct date keys
   the window, then fix the parser.
6. **Verify end-to-end on a real item with known data** before declaring done
   (an item you know has records, not an empty one).

## Image runtime contract

Use before configuring a third-party container/tool via env vars or config keys
you haven't confirmed it reads.

1. **Dump and read the entrypoint script** to enumerate exactly which env vars
   it handles:
   `docker run --rm --entrypoint="" <image> cat /entrypoint.sh`
   (or `sh -c 'cat $(command -v docker-entrypoint.sh)'`). A working setting
   often works via a *specific* CLI flag (`--webui-port=`), not a generic
   env→config mapping.
2. **If the setting isn't supported by the entrypoint, patch the config file
   directly** rather than passing an ignored env var. Use an `entrypoint:`
   wrapper that idempotently appends the setting before `exec`-ing the original
   entrypoint:

   ```sh
   cfg=/config/app.conf
   grep -q 'SettingKey' "$cfg" || printf '\nSettingKey=value\n' >> "$cfg"
   exec /entrypoint.sh "$@"
   ```

   Guard with `grep -q` so restarts don't accumulate duplicate lines.
3. **Verify on the real deployed host, not just locally.** A passing local
   config-validate does not prove the setting took effect — SSH in (or check
   live logs / API response) and confirm the observed behavior (e.g. the
   endpoint stops returning `Forbidden`).
4. **Distinguish the request paths.** When a service is reachable both directly
   (Docker network) and via a reverse proxy, a source-IP allowlist applies only
   to the direct path — the proxy presents its own IP. Decide per-path whether
   the bypass should apply, and never widen an allowlist to the proxy IP (it
   would bypass auth for all proxied traffic).

> Absorbed: verify-cli-premise, verify-cli-premise-before-tooling, verify-tool-premise, verify-api-schema-before-trust,
> verify-image-runtime-contract (2026-06)
