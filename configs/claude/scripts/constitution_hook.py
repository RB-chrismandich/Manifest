#!/usr/bin/env python3
"""PreToolUse hook: put the Code Constitution in front of the edit, not after it.

Wired on Read|Write|Edit|MultiEdit. For a source file in a supported language it
injects, as additionalContext:

  - every article and this language's ceilings, ONCE per language per
    session (the doctrine does not change between edits; paying for it on every
    edit would be the token waste the guide forbids)
  - the file's live measurements and any existing violations, EVERY time (these
    do change, and they are what makes the rule concrete for this file)

Advisory by construction: it never denies, never rewrites, and exits 0 on every
failure path. A hook that can block an edit is a hook that will one day block
the wrong edit; the blocking layers are pre-commit and CI, where a human can see
the whole change.
"""

import sys

# Keep the interpreter from writing __pycache__ next to the deployed scripts:
# an orphaned cache directory has previously broken the skill-naming gate and
# made apm decline to adopt a directory it did not fully own.
sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

PROG = "constitution_hook.py"
USAGE = """\
constitution_hook.py - PreToolUse hook injecting the Code Constitution

Reads the Claude Code PreToolUse payload on stdin. For Read/Write/Edit on a
file in a supported language, emits the articles and ceilings (once per
language per session) plus that file's measurements and existing violations.

Advisory only: never denies, never edits, always exits 0.

Usage: constitution_hook.py [--help]
"""

EDIT_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read"}
STATE_ROOT = Path(
    os.environ.get(
        "CONSTITUTION_STATE_DIR", Path.home() / ".claude" / "state" / "constitution"
    )
)
STATE_TTL_SECONDS = 7 * 24 * 3600
MAX_FINDINGS_SHOWN = 6


def main() -> int:
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(USAGE, end="")
        return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        context = _build_context(payload)
    # Fail-open: a hook must never break the tool it wraps. This is the
    # documented CON-007 exception, and the blast radius is one lost hint.
    # constitution: exempt C-ERR — hook must never break the tool it wraps
    except Exception:
        return 0
    if context:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "additionalContext": context,
                    }
                }
            )
        )
    return 0


def _build_context(payload: dict) -> str:
    tool = payload.get("tool_name") or ""
    if tool not in EDIT_TOOLS and tool not in READ_TOOLS:
        return ""
    tool_input = payload.get("tool_input") or {}
    raw_path = tool_input.get("file_path") or payload.get("file_path") or ""
    if not raw_path:
        return ""

    from constitution.registry import RegistryError, load

    try:
        registry = load()
    except RegistryError:
        return ""  # no rules readable means no advice, not a broken edit

    path = Path(raw_path)
    language = registry.language_for(path)
    if language is None:
        return ""

    first_time = _claim_language(payload.get("session_id") or "default", language.key)
    if tool in READ_TOOLS and not first_time:
        return ""  # reads are cheap to hook and expensive to narrate twice

    blocks = []
    if first_time:
        blocks.append(_doctrine(registry, language))
    situational = _situational(path, registry)
    if situational:
        blocks.append(situational)
    elif not first_time:
        return ""
    return "\n".join(blocks)


def _doctrine(registry, language) -> str:
    articles = " · ".join(f"{a.id} {a.title}" for a in registry.articles)
    ceilings = " · ".join(
        f"{name.replace('_', ' ')} {language.threshold(name)}"
        for name in (
            "file_lines",
            "class_lines",
            "function_lines",
            "methods_per_class",
            "parameters",
        )
        if language.threshold(name)
    )
    return (
        f"Code Constitution v{registry.version} applies to this {language.key} change. "
        f"Full text: ~/.claude/references/{language.annex}\n"
        f"{articles}\n"
        f"Ceilings ({language.key}): {ceilings}. Crossing one means split, not suppress.\n"
        f"Structured payloads (JSON/YAML/Markdown/SQL) belong in {', '.join(language.data_dirs)}/ "
        f"and load through one loader — never a source literal.\n"
        "Before writing: search for an existing implementation, write the failing test first, "
        "type and validate every boundary, and delete what this change obsoletes."
    )


def _situational(path: Path, registry) -> str:
    if not path.is_file():
        return (
            "New file: put its test at the mirroring test path first, give it one named "
            "responsibility, and keep any data payload out of the source."
        )

    from constitution.checks import run_checks
    from constitution.findings import render_context
    from constitution.source import SourceFile

    src = SourceFile.load(path, registry)
    # Advisory checks are excluded here even though they run everywhere else:
    # this repo carries ~1900 advisory findings, and an injection dominated by
    # missing-docstring notes would bury the structural violations that matter.
    gating = [cid for cid, check in registry.checks.items() if not check.advisory]
    findings = run_checks(src, registry, only=gating)
    if not findings:
        return f"{path.name} is {src.line_count} lines and currently clean against the constitution."
    return (
        f"{path.name} is {src.line_count} lines with {len(findings)} existing violation(s) "
        f"you are about to build on:\n{render_context(findings, limit=MAX_FINDINGS_SHOWN)}"
    )


def _claim_language(session_id: str, language_key: str) -> bool:
    """True the first time this session touches this language. Best-effort."""
    try:
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        _prune(STATE_ROOT)
        state_file = STATE_ROOT / f"{_safe(session_id)}.json"
        seen = (
            json.loads(state_file.read_text(encoding="utf-8"))
            if state_file.is_file()
            else []
        )
        if language_key in seen:
            return False
        seen.append(language_key)
        state_file.write_text(json.dumps(seen), encoding="utf-8")
        return True
    except OSError:
        # Unwritable state means the doctrine repeats rather than disappears.
        return True


def _prune(root: Path) -> None:
    cutoff = time.time() - STATE_TTL_SECONDS
    for stale in root.glob("*.json"):
        try:
            if stale.stat().st_mtime < cutoff:
                stale.unlink()
        except OSError:
            continue


def _safe(value: str) -> str:
    return (
        "".join(c if c.isalnum() or c in "-_" else "_" for c in value)[:96] or "default"
    )


if __name__ == "__main__":
    sys.exit(main())
