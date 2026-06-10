---
name: verify-cli-premise
description: Use before designing a skill, hook, spec, or plan around a CLI command or binary — verify it actually exists and behaves headlessly before building on it.
---
# Verify a CLI Premise Before Building On It

Multiple times a design was anchored to a command that either didn't exist
(`agi`/`antigravity`) or existed under a different spelling (`agy`) that the
first check missed. Verify the load-bearing CLI assumption FIRST — never write a
spec/skill/hook that calls a command you haven't confirmed runs.

1. **Confirm the binary exists, and try spelling variants.** Don't conclude
   "no such tool" from one name. Check several:
   ```bash
   for b in agy agi antigravity ag tool-cli; do
     p=$(command -v "$b" 2>/dev/null) && echo "found: $b -> $p ($("$b" --version 2>&1 | head -1))"
   done
   ```
   Also check common install dirs (`~/.local/bin`, Homebrew, `/usr/local/bin`)
   and whether an installed app ships a CLI.
2. **Read its actual subcommands/flags** (`<tool> --help`). Do NOT assume a
   `review`/`run` subcommand exists — many "agent" CLIs are just headless
   `-p/--print` prompt runners with no domain subcommands.
3. **Smoke-test headless behavior** before wiring it into automation. Confirm it:
   reads the prompt from **stdin**, prints a clean result, exits 0, is
   authenticated, and does **not** hang on a TTY/permission prompt. Bound it:
   ```bash
   echo "Reply with exactly: OK" | timeout 60 <tool> -p 2>&1; echo "exit=$?"
   ```
   (macOS lacks `timeout`; use a background PID + watchdog `kill`.)
4. **If the premise is false, say so and re-anchor.** Don't silently encode a
   command that can't run. Offer the realistic target (existing tool, a skill, a
   thin wrapper) and get agreement before designing.
5. **Record the verified facts** (exact path, version, stdin behavior, auth) so
   the spec/plan cites reality, not assumption.
