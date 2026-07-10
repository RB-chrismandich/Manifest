"""Run persistence and audit (FR-010; research D7).

Runs live in self-contained dirs under
``${MANIFEST_STATE_ROOT:-~/.manifest}/cddl/runs/<repo-slug>/<run-id>/``
(chmod 700, keep-everything). Audit events append through the existing
``audit_log.sh`` (redaction, fail-open) with CDDL_AUDIT_FILE exported as
AUDIT_LOG_FILE — audit_log.sh's generic file target
(contracts/cli-interface.md).
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import string
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

AUDIT_SCRIPT = Path(__file__).resolve().parent.parent / "audit_log.sh"


def utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_state_root() -> Path:
    return Path(os.environ.get("MANIFEST_STATE_ROOT") or Path.home() / ".manifest")


def default_audit_file() -> str:
    return os.environ.get(
        "CDDL_AUDIT_FILE", str(Path.home() / ".claude" / "cddl_audit.jsonl")
    )


def repo_slug(repo_root: str | Path) -> str:
    """Human-readable, filesystem-safe, collision-resistant repo key."""
    real = str(Path(repo_root).resolve())
    digest = hashlib.sha256(real.encode()).hexdigest()[:8]
    name = Path(real).name or "repo"
    safe = "".join(c if c.isalnum() or c in "._-" else "-" for c in name)
    return f"{safe}-{digest}"


def new_run_id(now: datetime | None = None) -> str:
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    suffix = "".join(
        secrets.choice(string.ascii_lowercase + string.digits) for _ in range(4)
    )
    return f"{stamp}-{suffix}"


class RunStore:
    """Filesystem accessor for one run directory."""

    def __init__(self, state_root, repo_root, run_id: str | None = None):
        self.repo_root = Path(repo_root).resolve()
        self.slug = repo_slug(self.repo_root)
        self.runs_root = Path(state_root) / "cddl" / "runs" / self.slug
        self.run_id = run_id or new_run_id()
        self.run_dir = self.runs_root / self.run_id

    # -- lifecycle -----------------------------------------------------------

    def create(self) -> RunStore:
        self.run_dir.mkdir(parents=True, exist_ok=False)
        os.chmod(self.run_dir, 0o700)
        (self.run_dir / "iterations").mkdir()
        return self

    @classmethod
    def open(cls, state_root, repo_root, run_id: str) -> RunStore:
        store = cls(state_root, repo_root, run_id=run_id)
        if not (store.run_dir / "state.json").is_file():
            from . import PreflightError

            raise PreflightError(f"no such run: {run_id} (under {store.runs_root})")
        return store

    @classmethod
    def find(cls, state_root, run_id: str) -> RunStore | None:
        """Locate a run by its globally-unique id across all repo slugs —
        lets `answer`/`status --run` work from outside the target repo."""
        runs_base = Path(state_root) / "cddl" / "runs"
        if not runs_base.is_dir():
            return None
        matches = [
            p for p in runs_base.glob(f"*/{run_id}") if (p / "state.json").is_file()
        ]
        if not matches:
            return None
        if len(matches) > 1:
            from . import PreflightError

            raise PreflightError(
                f"run id {run_id} is ambiguous across repos: "
                + ", ".join(str(m) for m in matches)
            )
        state = json.loads((matches[0] / "state.json").read_text(encoding="utf-8"))
        return cls(state_root, state["repo_root"], run_id=run_id)

    @classmethod
    def latest(cls, state_root, repo_root) -> RunStore | None:
        """Newest run for this repo (run-ids are UTC-timestamp-prefixed)."""
        probe = cls(state_root, repo_root)
        if not probe.runs_root.is_dir():
            return None
        candidates = sorted(
            (p for p in probe.runs_root.iterdir() if (p / "state.json").is_file()),
            key=lambda p: p.name,
        )
        if not candidates:
            return None
        return cls(state_root, repo_root, run_id=candidates[-1].name)

    # -- state ---------------------------------------------------------------

    def write_state(self, state: dict) -> None:
        tmp = self.run_dir / ".state.json.tmp"
        tmp.write_text(
            json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(tmp, self.run_dir / "state.json")

    def read_state(self) -> dict:
        return json.loads((self.run_dir / "state.json").read_text(encoding="utf-8"))

    # -- files ---------------------------------------------------------------

    def write_text(self, rel: str, text: str) -> Path:
        path = self.run_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def iteration_dir(self, n: int) -> Path:
        d = self.run_dir / "iterations" / str(n)
        d.mkdir(parents=True, exist_ok=True)
        return d

    # -- audit (fail-open, FR-010) --------------------------------------------

    def audit(self, event: str, **fields) -> None:
        record = {
            "ts": utcnow_iso(),
            "component": "cddl",
            "event": event,
            "run_id": self.run_id,
            "repo": str(self.repo_root),
            **fields,
        }
        try:
            env = dict(os.environ)
            env["AUDIT_LOG_FILE"] = default_audit_file()
            subprocess.run(
                ["bash", str(AUDIT_SCRIPT), "append", json.dumps(record)],
                env=env,
                capture_output=True,
                timeout=10,
                check=False,
            )
        except Exception as exc:
            print(f"cddl-loop: warning: audit append failed: {exc}", file=sys.stderr)
