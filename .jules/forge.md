## 2025-06-10 - ai-hooks-integration

**Learning:** `merge_hooks.py` completely dropped the `--command` parameter for `opencode` tools, meaning OpenCode
plugins were generated without any actual hooked logic. This occurred because OpenCode generated a template string
instead of parsing JSON, bypassing the core command injection logic.
**Action:** Always verify that CLI parameters are not conditionally bypassed for newer or alternative runtime tools. For
templates targeting Node/JS runtimes, ensure we inject the command dynamically via format strings and execute it
gracefully with robust `try/catch` wrappers.

## 2026-06-07 - issue-triage

**Learning:** Python scripts often format output as shell variable assignments intended to be sourced. Executing this
output dynamically via `eval` introduces command injection risks in bash scripts if the python code or input files are
altered.
**Action:** Configure automated checks to flag `eval "$(..."` or `eval \`...\`` patterns, especially those consuming
output from other commands. Use a `while IFS=` loop combined with a `case` whitelist to securely parse key-value
configuration directly into the shell environment without dynamic evaluation.

## 2026-06-12 - command-injection-eval

**Learning:** Hardcoding string replacements based on expected dynamic output (like `brew shellenv`) introduces
brittleness and is unsafe under `set -u` contexts. Variables like `MANPATH` may be unbound, causing a script crash.
**Action:** Prefer native bash process substitution (e.g. `source <(cmd)`) over manual string parsing or `eval "$(cmd)"`
when integrating system environment configs: it avoids brittle parsing/double-evaluation and `set -u` unbound-variable
crashes. Note `source <(cmd)` still executes whatever `cmd` outputs — the trust boundary is the same as `eval`, so only
use it with trusted producers.

## 2026-06-14 - ai-hooks-integration

**Learning:** Empty JavaScript optional catch bindings (like `catch { ... }`) silently swallow exceptions during hook
execution. This obscures critical failures (like WebSocket initialization or event delivery) in generated plugins and
violates our explicit routing and graceful degradation constraints.
**Action:** Configure automated checks to flag empty or bindingless `catch` blocks in generated JavaScript templates.
Ensure all catch statements explicitly capture the error object (e.g. `catch (e) { ... }`) and either log the error
message or correctly fallback/propagate it.

## 2026-06-21 - Forge Missing Init

**Learning:** When adopting the Forge persona, any explicit instruction to read `.jules/forge.md`
accompanied by the caveat `(create this file if it is missing)` implies a strict requirement to
establish the file structure, even if no critical learnings are discovered during the subsequent
execution that warrant a journal entry. Failing to create the empty/initial file violates the
strictness of the architectural persona.

**Action:** When acting as Forge, unconditionally create the `.jules/forge.md` file (e.g., using
`touch`) before performing any analysis, ensuring the base structural requirement is met regardless
of the audit's outcome.

## 2025-06-18 - json-parsing-overhead

**Learning:** Catching `ValueError` or `JSONDecodeError` exceptions when calling `json.loads` on non-JSON strings
creates significant performance overhead, especially in hooks or large parsing pipelines. Relying solely on `try/except`
for invalid CLI output or IPC is inefficient.
**Action:** Configure automated checks to enforce fast-path JSON validation (e.g., stripping whitespace and checking
if the first character is a valid JSON opening char like '{', '[', '"', 't', 'f', 'n', or a digit) before calling
`json.loads` to bypass exception overhead for obvious non-JSON strings. Ensure exceptions are not silently swallowed
by debug-only loggers.

## 2026-10-24 - JSON Fast-Path Optimization

**Learning:** Replacing standard, robust try/except blocks (like `json.JSONDecodeError`)
with brittle heuristic fast-paths (like explicit `isinstance` checks and generator
expressions to find the first character) in an attempt to optimize performance degrades
maintainability and violates the 'boring over clever' architectural philosophy. This is
especially true when the fast-path adds unnecessary type-checking boilerplate to standard
library functions guaranteed to return strings.

**Action:** Avoid replacing explicit exception handling blocks with clever heuristics
unless in a proven hot-loop where the exception overhead causes a measurable bottleneck.
Prioritize native, readable error routing over micro-optimizations.

## 2026-10-24 - JSON Parsing Overhead vs Robustness

**Learning:** Replacing standard, robust try/except blocks (like `json.JSONDecodeError`) with brittle heuristic
fast-paths (like explicit `isinstance` checks and checking the first character) degrades maintainability and violates
the 'boring over clever' architectural philosophy. When removing these heuristics and restoring native exception
routing, we must still ensure we validate the parsed payload (e.g. `isinstance(parsed, (dict, list))`) so that valid
JSON primitives do not bypass downstream expectations.

**Action:** Audit and revert scripts using the brittle `first_char in '{['` heuristic before `json.loads`. Replace
them with direct `try...except json.JSONDecodeError` blocks followed by `isinstance` validation to prevent primitives
from causing type errors.

## 2026-10-24 - Verification Gate Eval Rewrite

**Learning:** Using `eval` to interpolate unescaped variables like file paths
(e.g. `eval "${cmd} \"${packet}\""`) creates a severe command injection
vulnerability and violates core safety constraints.
**Action:** Replace `eval` with proper Bash array parsing and safe array
expansion (`read -r -a cmd_arr <<< "$cmd_str"` followed by
`"${cmd_arr[@]+"${cmd_arr[@]}"}" "$packet"`) to execute dynamic commands
securely without a subshell string evaluation.

## 2026-10-24 - Handling Duplicate Architectural PRs

**Learning:** When a PR is rejected because it is superseded by a broader active architectural refactor
(like #832 replacing multiple instances of brittle fast-paths and cleaning up tests), applying a strict
subset of those changes as a separate PR creates churn and duplicate effort.
**Action:** When a PR is closed as subsumed or obsolete, acknowledge the active architectural direction,
log any newly discovered broader scope context in `.jules/forge.md` to avoid future duplication, and
safely terminate execution without re-opening a duplicate PR.
