---
name: verify-cli-premise-before-tooling
description: Before designing a skill, hook, or command that wraps an external CLI/binary, verify the binary actually exists on PATH and inspect its real subcommands instead of assuming
---
# Verify CLI Premise Before Building Tooling

Use whenever a request asks you to "wrap", "integrate with", or "add a command to" a named CLI/binary (e.g. `agi spec-review`, `agy review`). Load-bearing premises about external tools are the most common cause of designing-on-sand.

1. **Check existence first, before any design.** Run `command -v <name>` and `<name> --version`. Try plausible spelling variants the user might mean (`agi` vs `agy`, hyphen vs underscore) — a missed variant once made a real tool look nonexistent.
2. **If absent, do not encode it into a spec.** Writing `<name> <subcommand>` into a design when `<name>` is not on PATH specifies a command that cannot run. Surface the gap explicitly and propose the repo-native alternative (skill + reusable engine script) instead of inventing a binary.
3. **If present, inspect real capabilities.** Run `<name> --help` and the relevant `<name> <subcommand> --help`; confirm the subcommand you intend to call exists and reads input the way you assume (argv vs stdin). Never assume a subcommand from the tool's name.
4. **Distinguish the binary from the IDE/app.** A symlink-only config dir (e.g. `configs/<tool>/` → `../claude/`) means the tool inherits config but provides no CLI — it is not a review agent. Confirm whether the thing is a binary, a daemon, or just an IDE before promising it can do work.
5. **Hold the line under repeated pushback.** If the user re-requests wrapping a nonexistent binary, restate the factual wall (binary absent) and the alternative that serves their real goal; design the engine front-end-agnostic so a future real binary can wrap it in a few lines for free.
6. **Re-verify after environment changes.** A premise true last week (agent running, socket bound) may be false now — re-probe before recommending a path that depends on it.
