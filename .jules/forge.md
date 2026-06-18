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

## 2025-06-18 - json-parsing-overhead

**Learning:** Catching `ValueError` or `JSONDecodeError` exceptions when calling `json.loads` on non-JSON strings
creates significant performance overhead, especially in hooks or large parsing pipelines. Relying solely on `try/except`
for invalid CLI output or IPC is inefficient.
**Action:** Configure automated checks to enforce fast-path JSON validation (e.g., stripping whitespace and checking
if the first character is a valid JSON opening char like '{', '[', '"', 't', 'f', 'n', or a digit) before calling
`json.loads` to bypass exception overhead for obvious non-JSON strings. Ensure exceptions are not silently swallowed
by debug-only loggers.
