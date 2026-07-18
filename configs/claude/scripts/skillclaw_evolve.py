#!/usr/bin/env python3
"""Distill SKILL.md candidates from ingested sessions via a headless LLM CLI.

Replaces the retired `skillclaw evolve` binary. Map-reduces sessions through the
LLM CLI named by `EVOLVE_CLI` (default `claude`, Max-backed): chunks that exceed
the token budget are distilled independently (map), then merged (reduce). No
proxy, no API key. The CLI is a swappable seam; the session source
(~/.claude/projects/**/*.jsonl transcripts) is not — see subprocess_runner().

Usage:
    skillclaw_evolve.py <sessions_dir> <evolved_dir> [--template FILE]
        [--token-budget N]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

DEFAULT_TOKEN_BUDGET = 100_000
DEFAULT_CHUNK_TIMEOUT = 600  # seconds per `claude -p` chunk (FR-010)
_SKILL_RE = re.compile(r"~~~skill name=(?P<name>[^\n]+)\n(?P<body>.*?)~~~", re.DOTALL)


def _load_audit():
    """Import the audit logger lazily; return None if unavailable (fail-open)."""
    try:
        import skillclaw_audit

        return skillclaw_audit
    except Exception:
        return None


def _fmt_elapsed(s: float) -> str:
    s = round(s)
    return f"{s // 60}m{s % 60:02d}s" if s >= 60 else f"{s}s"


def estimate_tokens(text: str) -> int:
    """Cheap heuristic: ~4 chars per token."""
    return len(text) // 4


def _render_session(s: dict) -> str:
    lines = [f"### session {s.get('session_id', '?')}"]
    for turn in s.get("turns", []):
        for b in turn["blocks"]:
            if b["kind"] in ("text", "thinking"):
                lines.append(f"[{turn['role']}/{b['kind']}] {b['text']}")
            elif b["kind"] == "tool_use":
                lines.append(f"[tool_use {b['name']}] {json.dumps(b['input'])}")
            elif b["kind"] == "tool_result":
                lines.append(f"[tool_result err={b['is_error']}] {b['output']}")
    return "\n".join(lines)


def load_sessions(sessions_dir) -> list[dict]:
    sessions_dir = Path(sessions_dir).expanduser()
    out = []
    for f in sorted(sessions_dir.glob("*.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return out


def build_prompt(template: str, sessions: list[dict], library_names: list[str]) -> str:
    library = "\n".join(f"- {n}" for n in library_names) or "(empty)"
    rendered = "\n\n".join(_render_session(s) for s in sessions) or "(none)"
    return template.replace("{{LIBRARY}}", library).replace("{{SESSIONS}}", rendered)


def parse_candidates(output: str) -> list[dict]:
    return [
        {"name": m.group("name").strip(), "content": m.group("body")}
        for m in _SKILL_RE.finditer(output)
    ]


def chunk_sessions(sessions: list[dict], token_budget: int) -> list[list[dict]]:
    """Greedily pack sessions into chunks whose rendered size stays under budget.

    A single session larger than the budget gets its own chunk (it cannot be
    split further here; the renderer already truncated tool noise upstream).
    """
    if not sessions:
        return []
    chunks: list[list[dict]] = []
    current: list[dict] = []
    current_tokens = 0
    for s in sessions:
        cost = estimate_tokens(_render_session(s))
        if current and current_tokens + cost > token_budget:
            chunks.append(current)
            current, current_tokens = [], 0
        current.append(s)
        current_tokens += cost
    if current:
        chunks.append(current)
    return chunks


def _chunk_timeout() -> int:
    """Per-chunk wall-clock bound for `claude -p` (FR-010). Env-overridable.

    Clamped to >=1 so a zero/negative override can't fail every chunk instantly.
    """
    try:
        return max(
            1, int(os.environ.get("SKILLCLAW_CHUNK_TIMEOUT", DEFAULT_CHUNK_TIMEOUT))
        )
    except ValueError:
        return DEFAULT_CHUNK_TIMEOUT


def subprocess_runner(prompt: str) -> str:
    """Default runner: invoke headless `"${EVOLVE_CLI}" -p` (Max-backed).

    The CLI binary is a role-named, injectable seam (llm-invoke-stdin pattern):
    `EVOLVE_CLI` env var, defaulting to `claude`. Swapping vendors (e.g.
    claude -> gemini) is a one-line env-var change; no code edit required.
    This seam covers the LLM invocation ONLY — the session data this prompt is
    built from (~/.claude/projects/**/*.jsonl, ingested by skillclaw_ingest.py)
    is Claude Code transcript format and is claude-specific by design, not
    part of this seam.

    The prompt is fed via stdin, not as an argv argument, so large transcript
    windows (a chunk can approach token_budget * 4 chars) never hit the OS
    ARG_MAX "Argument list too long" limit (1 MB on macOS). The CLI reads the
    prompt from stdin when no positional prompt is given (true of `claude -p`;
    verify equivalent stdin behavior before swapping to another vendor's CLI).

    Bounded by a per-chunk timeout so a hung CLI can never block evolve
    forever; a timeout raises the same RuntimeError shape as a non-zero exit,
    so promote.sh's existing fail-continue path applies.
    """
    cli = os.environ.get("EVOLVE_CLI", "claude")
    timeout = _chunk_timeout()
    try:
        proc = subprocess.run(
            [cli, "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"{cli} -p timed out after {timeout}s (chunk abandoned)"
        ) from e
    if proc.returncode != 0:
        raise RuntimeError(f"{cli} -p failed: {proc.stderr.strip()}")
    return proc.stdout


def write_candidates(candidates: list[dict], evolved_dir: Path) -> list[str]:
    evolved_dir = Path(evolved_dir).expanduser()
    written = []
    for c in candidates:
        d = evolved_dir / c["name"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "SKILL.md").write_text(c["content"], encoding="utf-8")
        written.append(c["name"])
    return written


_DESC_MAX = 200
_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---", re.DOTALL)
_DESC_LINE_RE = re.compile(
    r"^description:\s*(.+?)(?=\n\S|\Z)", re.MULTILINE | re.DOTALL
)


def _skill_description(skill_md: Path):
    """Best-effort description from SKILL.md frontmatter; None on any failure.

    Fail-open by design (contracts/library-prompt.md): a broken skill file
    must never abort an evolve run — it just renders as a name-only line.
    """
    try:
        m = _FRONTMATTER_RE.match(skill_md.read_text(encoding="utf-8"))
        if not m:
            return None
        d = _DESC_LINE_RE.search(m.group(1))
        if not d:
            return None
        raw = d.group(1)
        # Block scalars (description: | / > with optional chomping/indent)
        # put only the marker on the key line — drop it, keep the body.
        first, _, rest = raw.partition("\n")
        if re.fullmatch(r"[|>][+-]?\d*", first.strip()):
            raw = rest
        # Flatten (multi-line YAML values included) and bound prompt cost.
        desc = " ".join(raw.split())
        return desc[:_DESC_MAX] if desc else None
    except OSError:
        return None


def _library_names(skills_dir: Path) -> list[str]:
    """Library entries under a skills root: 'name — description' per skill.

    Descriptions let the model match by purpose (not just name) so absorbed/
    deleted variants are not re-proposed under new names (FR-005). Falls back
    to the bare name when no description is parsable.
    """
    base = Path(skills_dir).expanduser()
    if not base.exists():
        return []
    entries = []
    for p in sorted(base.glob("*/SKILL.md")):
        desc = _skill_description(p)
        entries.append(f"{p.parent.name} — {desc}" if desc else p.parent.name)
    return entries


def evolve(
    sessions_dir,
    evolved_dir,
    template_path,
    *,
    committed_dir=None,
    token_budget=DEFAULT_TOKEN_BUDGET,
    runner=subprocess_runner,
    run_id=None,
    audit=None,
) -> dict:
    """Map-reduce sessions into SKILL.md candidates. Returns a summary dict.

    The prompt's "existing library" is the committed library (committed_dir) so
    the model does not re-propose already-merged skills; it falls back to
    evolved_dir only when no committed library is supplied.
    """
    sessions = load_sessions(sessions_dir)
    template = Path(template_path).expanduser().read_text(encoding="utf-8")
    library = _library_names(
        committed_dir if committed_dir is not None else evolved_dir
    )
    chunks = chunk_sessions(sessions, token_budget)
    # Emit stage_start before the empty-sessions short-circuit so --status reflects
    # that evolve ran (and skipped) rather than showing a stale prior stage.
    audit_mod = audit if audit is not None else (_load_audit() if run_id else None)
    if audit_mod and run_id:
        audit_mod.log(run_id, "evolve", "stage_start", chunks=len(chunks))
    if not sessions:
        return {"candidates": 0, "chunks": 0, "written": []}

    mapped: list[dict] = []
    start = time.monotonic()
    prev_elapsed = 0.0
    for idx, chunk in enumerate(chunks, 1):
        out = runner(build_prompt(template, chunk, library))
        mapped.extend(parse_candidates(out))
        if audit_mod and run_id:
            elapsed = time.monotonic() - start
            chunk_seconds = round(elapsed - prev_elapsed, 1)
            prev_elapsed = elapsed
            audit_mod.log(
                run_id,
                "evolve",
                "chunk_done",
                i=idx,
                total=len(chunks),
                chunk_seconds=chunk_seconds,
                elapsed_s=round(elapsed, 1),
            )
            _, label = audit_mod.compute_eta(idx, len(chunks), elapsed)
            print(
                f"[skillclaw] evolve · chunk {idx}/{len(chunks)} · {_fmt_elapsed(elapsed)} · {label}",
                file=sys.stderr,
            )

    # reduce: dedupe by name (last write wins); a single chunk skips a 2nd call
    if len(chunks) > 1 and mapped:
        deduped = {}
        for c in mapped:
            deduped[c["name"]] = c
        mapped = list(deduped.values())

    written = write_candidates(mapped, evolved_dir)
    return {"candidates": len(written), "chunks": len(chunks), "written": written}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions_dir")
    ap.add_argument("evolved_dir")
    ap.add_argument("--template", default="~/.claude/prompts/skillclaw_evolve.md")
    ap.add_argument(
        "--committed-dir",
        help="committed skill library shown to the model (avoids re-proposals)",
    )
    ap.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    ap.add_argument(
        "--run-id", default=None, help="audit run id; enables per-chunk status logging"
    )
    ap.add_argument(
        "--chunk-timeout",
        type=int,
        default=None,
        help="seconds per `claude -p` chunk (FR-010); wins over "
        f"SKILLCLAW_CHUNK_TIMEOUT, default {DEFAULT_CHUNK_TIMEOUT}",
    )
    args = ap.parse_args(argv)
    if args.chunk_timeout is not None:
        # Export to the env seam subprocess_runner reads at call time, so the
        # override reaches every chunk without threading it through evolve().
        os.environ["SKILLCLAW_CHUNK_TIMEOUT"] = str(args.chunk_timeout)
    try:
        summary = evolve(
            args.sessions_dir,
            args.evolved_dir,
            args.template,
            committed_dir=args.committed_dir,
            token_budget=args.token_budget,
            run_id=args.run_id,
        )
    except (RuntimeError, FileNotFoundError) as e:
        print(f"skillclaw_evolve: {e}", file=sys.stderr)
        return 1
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
