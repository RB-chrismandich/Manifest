"""Implementer-candidate parsing, write confinement, atomic apply
(FR-005, FR-007, FR-011, FR-017; research D10).

Contract: specs/482-critic-dev-loop/contracts/candidate-format.md. Validation
is all-or-nothing and happens before any write: one bad path rejects the whole
candidate with zero writes, keeping iterations atomic and verdicts unambiguous.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .verdicts import extract_fenced_blocks, strip_fenced_blocks

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:[\\/]")


@dataclass
class FileBlock:
    path: str
    content: str
    delete: bool = False


@dataclass
class CandidateChange:
    files: list = field(default_factory=list)  # list[FileBlock]
    notes: str = ""
    ok: bool = False
    deficiency: str | None = None  # rejection reason when not ok


def _validate_path(path: str, repo_real: Path) -> str | None:
    """Return a rejection reason, or None when the path is confined."""
    if not path:
        return "empty path"
    if " " in path:
        return f"path contains a space (invalid in v1 grammar): {path!r}"
    if "\\" in path:
        # A backslash is a filename char on POSIX but a separator on Windows;
        # sequences like foo\..\bar would sail past the `..` segment check.
        # Fail closed (llm-audit-traversal): no backslashes in v1 paths.
        return f"path contains a backslash (invalid in v1 grammar): {path!r}"
    if path.startswith("/") or _DRIVE_PREFIX.match(path):
        return f"absolute path not allowed: {path}"
    parts = Path(path).parts
    if ".." in parts:
        return f"upward traversal not allowed: {path}"
    if ".git" in parts:
        return f"writes into .git/ are not allowed: {path}"
    # Symlink-escape check: the deepest existing ancestor of the parent dir is
    # realpath-resolved; it must stay inside the repo realpath (llm-audit-traversal).
    parent_real = (repo_real / path).parent.resolve()
    if not parent_real.is_relative_to(repo_real):
        return f"path escapes the repository via its parent directory: {path}"
    return None


def parse_candidate(raw: str, repo_root: str | Path) -> CandidateChange:
    """Parse file blocks and validate confinement; never writes."""
    repo_real = Path(repo_root).resolve()
    blocks = extract_fenced_blocks(raw or "")
    files: list[FileBlock] = []
    # Contract: prose OUTSIDE blocks is retained as notes — block bodies must
    # not leak into notes (they would be duplicated into critic prompts).
    notes = strip_fenced_blocks(raw or "")

    def reject(reason: str) -> CandidateChange:
        return CandidateChange(notes=notes, deficiency=reason)

    for info, content in blocks:
        tokens = info.split(" ", 1)
        kind = tokens[0]
        if kind not in ("cddl-file", "cddl-delete"):
            continue  # foreign fences are prose, not candidate blocks
        spec = tokens[1].strip() if len(tokens) > 1 else ""
        problem = _validate_path(spec, repo_real)
        if problem:
            return reject(f"confinement violation: {problem}")
        if kind == "cddl-delete":
            if content.strip():
                return reject(f"cddl-delete block for {spec} must have an empty body")
            files.append(FileBlock(path=spec, content="", delete=True))
        else:
            body = content
            if body and not body.endswith("\n"):
                body += "\n"
            files.append(FileBlock(path=spec, content=body))

    if not files:
        return reject(
            "no-candidate: implementer output contained zero cddl-file/"
            "cddl-delete blocks"
        )
    return CandidateChange(files=files, notes=notes, ok=True)


def apply_candidate(
    cand: CandidateChange, repo_root: str | Path, backup_dir: str | Path | None = None
) -> list[str]:
    """Apply a validated candidate; returns the written/deleted paths in order.

    Writes are atomic per file (temp file + same-directory rename). When
    backup_dir is given, the pre-image of every existing file about to be
    overwritten or deleted is copied there first — the rollback path for
    --allow-dirty runs, whose uncommitted edits git cannot recover.
    """
    if not cand.ok:
        raise ValueError("refusing to apply a rejected candidate")
    repo = Path(repo_root)
    written: list[str] = []
    for block in cand.files:
        target = repo / block.path
        if backup_dir is not None and (target.is_file() or target.is_symlink()):
            pre_image = Path(backup_dir) / block.path
            pre_image.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, pre_image, follow_symlinks=False)
        if block.delete:
            if target.exists() or target.is_symlink():
                target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.parent / f".{target.name}.cddl-tmp"
            tmp.write_text(block.content, encoding="utf-8")
            os.replace(tmp, target)
        written.append(block.path)
    return written


def serialize_candidate(cand: CandidateChange) -> str:
    """Stable digest of the effective change — prose notes excluded — so the
    loop can flag byte-identical consecutive candidates as stalls."""
    payload = [
        {"path": b.path, "content": b.content, "delete": b.delete} for b in cand.files
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
