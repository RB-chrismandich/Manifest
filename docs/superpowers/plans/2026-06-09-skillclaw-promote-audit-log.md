# SkillClaw Promote — Audit Log + Live Status/ETA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `skillclaw_promote` a durable JSONL audit history plus a live, queryable run-status snapshot with a rough ETA, without ever blocking the promote pipeline.

**Architecture:** A new `skillclaw_audit.py` module is the single source of truth for two files under `~/.skillclaw/`: an append-only `promote.log` (JSONL audit history) and an overwritten `status.json` (live snapshot + ETA). The shell orchestrator (`skillclaw_promote.sh`) writes run/stage events through its CLI; the Python evolver (`skillclaw_evolve.py`) writes per-chunk progress through its importable API. All audit calls are fail-open — any I/O error is swallowed so a promote run completes regardless.

**Tech Stack:** Python 3 (stdlib only: `json`, `os`, `datetime`, `pathlib`), Bash (`set -euo pipefail`), pytest, bats, shellcheck.

---

## Source Spec

`docs/superpowers/specs/2026-06-09-skillclaw-promote-audit-log-design.md` (Approved; reviewed by `agy` — 7 findings incorporated).

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `configs/claude/scripts/skillclaw_audit.py` | Logger + status/ETA engine. Owns both file formats, atomic writes, fail-open wrappers, CLI (`log`/`status`/`trim`). | **Create** |
| `configs/claude/scripts/skillclaw_evolve.py` | Add `--run-id`; emit `stage_start`/`chunk_done` per chunk + a live stderr progress line. | **Modify** |
| `configs/claude/scripts/skillclaw_promote.sh` | Mint `run_id`; log run/stage events + candidates + `pr_opened`; `--status` flag; finalization trap; `trim` once. | **Modify** |
| `tests/python/test_skillclaw_audit.py` | Unit tests for `compute_eta`, `log`, status reset, `render_status` (incl. stale), `trim` (atomic), fail-open, storage init. | **Create** |
| `tests/python/test_skillclaw_evolve.py` | Extend: chunk events update `status.json` with correct `chunk`/`total`. | **Modify** |
| `tests/bats/skillclaw_promote.bats` | Extend: `run_id` in log, `--status` render, stage events, trap-on-interrupt, unwritable-path-still-exits-0. | **Modify** |
| `docs/SKILLCLAW.md`, `CHANGELOG.md` | Document the audit log, `--status`, and live progress. | **Modify** |

### Conventions to follow (verified in-repo)

- Python CLI scripts: `from __future__ import annotations`, `def main(argv: list[str]) -> int`, `raise SystemExit(main(sys.argv[1:]))`, errors to stderr.
- pytest files start with `sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))` then import the module.
- Scripts are invoked as `python3 "${SCRIPT_DIR}/skillclaw_*.py"` — never bare on `PATH`.
- Atomic file writes use a `.tmp` sibling + `os.replace()`.
- Storage dir `~/.skillclaw/` is `chmod 700`; files are `chmod 600`.
- `run_id` format: `<UTC>-<pid>`, e.g. `20260609T230501Z-4821` (the timestamp has no `-`, so `rsplit("-", 1)` recovers the pid).
- Tests redirect storage via the `SKILLCLAW_AUDIT_DIR` env var (default `~/.skillclaw`).

---

## Task 1: Audit module skeleton — storage helpers + `compute_eta`

**Files:**
- Create: `configs/claude/scripts/skillclaw_audit.py`
- Test: `tests/python/test_skillclaw_audit.py`

`compute_eta` is a pure function — start here so the storage scaffolding (dir resolution, atomic write) lands with a trivially testable unit.

- [ ] **Step 1: Write the failing test**

Create `tests/python/test_skillclaw_audit.py`:

```python
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
import skillclaw_audit as audit  # noqa: E402


def test_compute_eta_estimating_until_two_chunks():
    assert audit.compute_eta(0, 12, 0)[1] == "estimating…"
    assert audit.compute_eta(1, 12, 14.2)[1] == "estimating…"


def test_compute_eta_guards_bad_inputs():
    # total <= done, and non-positive elapsed -> estimating, never negative/div0
    assert audit.compute_eta(5, 5, 60)[0] is None
    assert audit.compute_eta(6, 5, 60)[0] is None
    assert audit.compute_eta(3, 12, 0)[0] is None
    assert audit.compute_eta(3, 12, -1)[0] is None


def test_compute_eta_linear_projection():
    # (12-4) * (60/4) = 120s -> ~2m
    eta_s, label = audit.compute_eta(4, 12, 60)
    assert eta_s == 120
    assert label == "~2m left (est)"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_audit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'skillclaw_audit'`.

- [ ] **Step 3: Write the minimal implementation**

Create `configs/claude/scripts/skillclaw_audit.py`:

```python
#!/usr/bin/env python3
"""SkillClaw promote audit log + live status/ETA engine.

Single source of truth for two artifacts under ~/.skillclaw/:
  - promote.log : append-only JSONL audit history (one event per line)
  - status.json : overwritten snapshot of the current/last run + rough ETA

Fail-open by construction: every public function swallows I/O errors and returns
cleanly, so audit logging can never abort or delay a promote run.

CLI (always invoked as `python3 "${SCRIPT_DIR}/skillclaw_audit.py" <cmd>`):
    log <run_id> <stage> <event> [key=value ...]
    status
    trim [--max-runs N]

Env overrides (tests): SKILLCLAW_AUDIT_DIR (default ~/.skillclaw).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_HOME = "~/.skillclaw"
MAX_RUNS = 50
RUNNING, DONE, FAILED, STALE = "running", "done", "failed", "stale"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _audit_dir() -> Path:
    return Path(os.environ.get("SKILLCLAW_AUDIT_DIR", DEFAULT_HOME)).expanduser()


def _log_path() -> Path:
    return _audit_dir() / "promote.log"


def _status_path() -> Path:
    return _audit_dir() / "status.json"


def _ensure_storage() -> Path:
    """mkdir -p ~/.skillclaw (700) so a fresh install never silently logs nothing."""
    d = _audit_dir()
    d.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(d, 0o700)
    except OSError:
        pass
    return d


def _write_atomic(path: Path, data: str) -> None:
    """Write via a .tmp sibling + os.replace so concurrent reads never see a torn file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def compute_eta(chunks_done, chunks_total, elapsed_s):
    """Return (eta_s|None, label).

    `estimating…` until >=2 chunks are done and inputs are sane; otherwise a
    linear projection. Guards prevent negative/div-by-zero ETAs from corrupt or
    out-of-order status.
    """
    try:
        if chunks_done < 2 or chunks_total <= chunks_done or elapsed_s <= 0:
            return (None, "estimating…")
        eta_s = (chunks_total - chunks_done) * (elapsed_s / chunks_done)
        return (eta_s, "~%dm left (est)" % max(1, round(eta_s / 60)))
    except (TypeError, ValueError):
        return (None, "estimating…")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_audit.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_audit.py tests/python/test_skillclaw_audit.py
git commit -m "feat(skillclaw): audit module skeleton + compute_eta"
```

---

## Task 2: `log()` — append JSONL + update live `status.json` (no state bleed)

**Files:**
- Modify: `configs/claude/scripts/skillclaw_audit.py`
- Test: `tests/python/test_skillclaw_audit.py`

`log()` appends one audit line and folds the event into the live snapshot. A `run_start` — or any event whose `run_id` differs from the one in `status.json` — initializes a fresh snapshot instead of merging, so a new run never inherits the prior run's `pr_url`/metrics.

- [ ] **Step 1: Write the failing test**

Append to `tests/python/test_skillclaw_audit.py`:

```python
import json


def _read(p):
    return json.loads(Path(p).read_text())


def test_log_appends_jsonl_and_updates_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    audit.log("20260609T230501Z-4821", "-", "run_start",
              window_days=30, token_budget=100000, apply=True)
    log_lines = (tmp_path / "promote.log").read_text().splitlines()
    assert len(log_lines) == 1
    first = json.loads(log_lines[0])
    assert first["event"] == "run_start" and first["window_days"] == 30
    status = _read(tmp_path / "status.json")
    assert status["run_id"] == "20260609T230501Z-4821"
    assert status["state"] == "running"


def test_chunk_done_event_records_eta(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(rid, "evolve", "stage_start", chunks=12)
    audit.log(rid, "evolve", "chunk_done", i=4, total=12, chunk_seconds=15.0, elapsed_s=60)
    status = _read(tmp_path / "status.json")
    assert status["stage"] == "evolve"
    assert status["evolve"]["chunk"] == 4 and status["evolve"]["total"] == 12
    assert status["evolve"]["eta_s"] == 120
    assert status["evolve"]["eta_label"] == "~2m left (est)"


def test_new_run_id_resets_snapshot_no_state_bleed(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    audit.log("20260609T230501Z-1111", "promote", "pr_opened", url="https://x/pull/9")
    audit.log("20260609T235959Z-2222", "-", "run_start")  # different run_id
    status = _read(tmp_path / "status.json")
    assert status["run_id"] == "20260609T235959Z-2222"
    assert status["pr_url"] is None          # prior run's PR must not bleed in
    assert status["state"] == "running"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_audit.py -k "log or chunk or state_bleed" -v`
Expected: FAIL with `AttributeError: module 'skillclaw_audit' has no attribute 'log'`.

- [ ] **Step 3: Write the implementation**

Add to `configs/claude/scripts/skillclaw_audit.py` (after `compute_eta`):

```python
def _read_status() -> dict:
    try:
        return json.loads(_status_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _fresh_status(run_id: str) -> dict:
    now = _now_iso()
    return {
        "run_id": run_id,
        "started_at": now,
        "updated_at": now,
        "state": RUNNING,
        "stage": "-",
        "evolve": None,
        "totals": {"ingested": None, "candidates": None, "dropped": None},
        "pr_url": None,
    }


def _apply_event(status: dict, stage: str, event: str, fields: dict) -> dict:
    status["updated_at"] = _now_iso()
    if stage and stage != "-":
        status["stage"] = stage
    if event == "run_start":
        cfg = status.setdefault("config", {})
        for k in ("window_days", "token_budget", "apply"):
            if k in fields:
                cfg[k] = fields[k]
    elif event == "stage_start" and stage == "evolve":
        status["evolve"] = {"chunk": 0, "total": fields.get("chunks", 0),
                            "elapsed_s": 0, "eta_s": None, "eta_label": "estimating…"}
    elif event == "stage_end" and "ingested" in fields:
        status["totals"]["ingested"] = fields["ingested"]
    elif event == "chunk_done":
        done, total = fields.get("i", 0), fields.get("total", 0)
        elapsed = fields.get("elapsed_s", 0)
        eta_s, label = compute_eta(done, total, elapsed)
        status["evolve"] = {"chunk": done, "total": total, "elapsed_s": elapsed,
                            "eta_s": eta_s, "eta_label": label}
    elif event == "candidates":
        new = fields.get("new") or []
        changed = fields.get("changed") or []
        dropped = fields.get("dropped") or []
        status["totals"]["candidates"] = len(new) + len(changed)
        status["totals"]["dropped"] = len(dropped)
    elif event == "pr_opened":
        status["pr_url"] = fields.get("url")
    elif event == "run_end":
        status["state"] = fields.get("state", DONE)
        status["stage"] = "-"
        status["total_seconds"] = fields.get("total_seconds")
    elif event == "run_error":
        status["state"] = FAILED
        status["error_stage"] = stage
        status["message"] = fields.get("message")
    return status


def log(run_id, stage, event, **fields):
    """Append one JSONL audit line and update the live status snapshot. Fail-open."""
    try:
        _ensure_storage()
        line = {"ts": _now_iso(), "run_id": run_id, "stage": stage, "event": event}
        line.update(fields)
        with _log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(line) + "\n")
        try:
            os.chmod(_log_path(), 0o600)
        except OSError:
            pass
        current = _read_status()
        if event == "run_start" or current.get("run_id") != run_id:
            current = _fresh_status(run_id)
        _write_atomic(_status_path(), json.dumps(_apply_event(current, stage, event, fields), indent=2))
    except Exception:  # noqa: BLE001 - fail-open: never raise into the pipeline
        return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_audit.py -v`
Expected: PASS (all Task 1 + Task 2 tests).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_audit.py tests/python/test_skillclaw_audit.py
git commit -m "feat(skillclaw): audit log() with no-state-bleed status snapshot"
```

---

## Task 3: `render_status()` — one-glance summary + stale-pid detection

**Files:**
- Modify: `configs/claude/scripts/skillclaw_audit.py`
- Test: `tests/python/test_skillclaw_audit.py`

`render_status()` produces the human line for `--status`. If `state=="running"` but the pid embedded in `run_id` is no longer alive, it reports `stale` — a SIGKILL'd run that skipped the finalization trap must never show as a phantom running run.

- [ ] **Step 1: Write the failing test**

Append to `tests/python/test_skillclaw_audit.py`:

```python
def test_render_status_no_recent_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    assert audit.render_status() == "no recent run"


def test_render_status_running_evolve(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    monkeypatch.setattr(audit, "_pid_alive", lambda pid: True)
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(rid, "evolve", "stage_start", chunks=12)
    audit.log(rid, "evolve", "chunk_done", i=4, total=12, chunk_seconds=15.0, elapsed_s=60)
    out = audit.render_status()
    assert "evolve" in out and "chunk 4/12" in out and "~2m left (est)" in out


def test_render_status_stale_when_pid_dead(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    monkeypatch.setattr(audit, "_pid_alive", lambda pid: False)
    audit.log("20260609T230501Z-4821", "-", "run_start")
    assert "stale" in audit.render_status()


def test_render_status_done_summary(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(rid, "classify", "candidates", new=["a", "b", "c"], changed=[], dropped=[])
    audit.log(rid, "promote", "pr_opened", url="https://x/pull/7")
    audit.log(rid, "-", "run_end", state="done", total_seconds=252.4)
    out = audit.render_status()
    assert "done" in out and "3 candidates" in out and "PR https://x/pull/7" in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_audit.py -k render -v`
Expected: FAIL with `AttributeError: module 'skillclaw_audit' has no attribute 'render_status'`.

- [ ] **Step 3: Write the implementation**

Add to `configs/claude/scripts/skillclaw_audit.py` (after `log`):

```python
def _pid_from_run_id(run_id):
    try:
        return int(str(run_id).rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None


def _pid_alive(pid):
    if pid is None:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True   # exists but owned by another user
    except OSError:
        return False
    return True


def _fmt_secs(s):
    try:
        s = int(round(float(s)))
    except (TypeError, ValueError):
        return "?"
    return "%dm%02ds" % (s // 60, s % 60) if s >= 60 else "%ds" % s


def render_status():
    """One-glance human summary for --status. Fail-open -> 'no recent run'."""
    try:
        st = _read_status()
        if not st:
            return "no recent run"
        state = st.get("state")
        run_id = st.get("run_id", "?")
        short = str(run_id).split("-")[0][:13]
        if state == RUNNING and not _pid_alive(_pid_from_run_id(run_id)):
            state = STALE
        if state == RUNNING:
            ev = st.get("evolve") or {}
            stage = st.get("stage", "?")
            if stage == "evolve" and ev.get("total"):
                return ("run %s · evolve · chunk %s/%s · %s elapsed · %s"
                        % (short, ev.get("chunk"), ev.get("total"),
                           _fmt_secs(ev.get("elapsed_s")),
                           ev.get("eta_label", "estimating…")))
            return "run %s · %s · running" % (short, stage)
        if state == STALE:
            return "run %s · stale (no live process)" % short
        if state == FAILED:
            return "last run: failed · stage %s" % st.get("error_stage", "?")
        tot = st.get("totals", {})
        parts = ["last run: done"]
        if tot.get("candidates") is not None:
            parts.append("%s candidates" % tot["candidates"])
        if st.get("pr_url"):
            parts.append("PR %s" % st["pr_url"])
        if st.get("total_seconds") is not None:
            parts.append(_fmt_secs(st["total_seconds"]))
        return " · ".join(parts)
    except Exception:  # noqa: BLE001 - fail-open
        return "no recent run"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_audit.py -v`
Expected: PASS (all tests through Task 3).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_audit.py tests/python/test_skillclaw_audit.py
git commit -m "feat(skillclaw): render_status with stale-pid detection"
```

---

## Task 4: `trim()` — atomic retention to the last ~50 runs

**Files:**
- Modify: `configs/claude/scripts/skillclaw_audit.py`
- Test: `tests/python/test_skillclaw_audit.py`

`trim()` rewrites `promote.log` keeping only events for the most recent `max_runs` `run_id`s, written atomically so an interrupt mid-trim leaves the original intact.

- [ ] **Step 1: Write the failing test**

Append to `tests/python/test_skillclaw_audit.py`:

```python
def test_trim_keeps_only_recent_run_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    for i in range(5):
        audit.log("run-%d" % i, "-", "run_start")
    audit.trim(max_runs=2)
    rids = {json.loads(ln)["run_id"]
            for ln in (tmp_path / "promote.log").read_text().splitlines()}
    assert rids == {"run-3", "run-4"}


def test_trim_is_atomic_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    for i in range(3):
        audit.log("run-%d" % i, "-", "run_start")
    original = (tmp_path / "promote.log").read_text()

    def boom(*a, **k):
        raise OSError("simulated mid-trim crash")

    monkeypatch.setattr(audit.os, "replace", boom)
    audit.trim(max_runs=1)  # fail-open: swallows the error
    assert (tmp_path / "promote.log").read_text() == original  # untouched
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_audit.py -k trim -v`
Expected: FAIL with `AttributeError: module 'skillclaw_audit' has no attribute 'trim'`.

- [ ] **Step 3: Write the implementation**

Add to `configs/claude/scripts/skillclaw_audit.py` (after `render_status`):

```python
def trim(max_runs=MAX_RUNS):
    """Keep only events for the most recent max_runs run_ids. Atomic. Fail-open."""
    try:
        path = _log_path()
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        order, seen = [], set()
        for ln in lines:
            try:
                rid = json.loads(ln).get("run_id")
            except ValueError:
                continue
            if rid not in seen:
                seen.add(rid)
                order.append(rid)
        keep = set(order[-max_runs:])
        kept = []
        for ln in lines:
            try:
                if json.loads(ln).get("run_id") in keep:
                    kept.append(ln)
            except ValueError:
                continue
        _write_atomic(path, "\n".join(kept) + ("\n" if kept else ""))
    except Exception:  # noqa: BLE001 - fail-open
        return
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/python/test_skillclaw_audit.py -v`
Expected: PASS (all tests through Task 4).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_audit.py tests/python/test_skillclaw_audit.py
git commit -m "feat(skillclaw): atomic trim() retention to last 50 runs"
```

---

## Task 5: Fail-open hardening + storage auto-init + CLI entry

**Files:**
- Modify: `configs/claude/scripts/skillclaw_audit.py`
- Test: `tests/python/test_skillclaw_audit.py`

Add the CLI (`log`/`status`/`trim` with `key=value` field parsing — shell's only interface) and prove the two cross-cutting guarantees: an unwritable audit dir never raises, and storage auto-inits on a fresh machine.

- [ ] **Step 1: Write the failing test**

Append to `tests/python/test_skillclaw_audit.py`:

```python
def test_fail_open_on_unwritable_dir(tmp_path, monkeypatch):
    # Point the audit dir *inside* a regular file so mkdir raises NotADirectoryError.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(blocker / "sub"))
    audit.log("run-x", "-", "run_start")          # must not raise
    assert audit.render_status() == "no recent run"


def test_storage_auto_inits_when_absent(tmp_path, monkeypatch):
    target = tmp_path / "fresh" / "nested"        # does not exist yet
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(target))
    audit.log("run-1", "-", "run_start")
    assert (target / "promote.log").exists()
    assert (target / "status.json").exists()


def test_cli_log_parses_key_value_and_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rc = audit.main(["log", "run-1", "classify", "candidates",
                     'new=["a","b"]', "dropped=[]", "changed=[]"])
    assert rc == 0
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["totals"]["candidates"] == 2


def test_cli_status_and_trim(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    assert audit.main(["status"]) == 0
    assert capsys.readouterr().out.strip() == "no recent run"
    assert audit.main(["trim", "--max-runs", "10"]) == 0   # no log yet -> no-op, rc 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_audit.py -k "fail_open or auto_inits or cli" -v`
Expected: FAIL with `AttributeError: module 'skillclaw_audit' has no attribute 'main'`.

- [ ] **Step 3: Write the implementation**

Add to `configs/claude/scripts/skillclaw_audit.py` (after `trim`, before any `__main__` guard):

```python
def _parse_kv(pairs):
    """Parse `key=value` argv pairs; JSON-decode each value, else keep the string."""
    out = {}
    for p in pairs:
        if "=" not in p:
            continue
        k, v = p.split("=", 1)
        try:
            out[k] = json.loads(v)
        except ValueError:
            out[k] = v
    return out


def main(argv):
    if not argv or argv[0] == "status":
        print(render_status())
        return 0
    cmd, rest = argv[0], argv[1:]
    if cmd == "trim":
        mx = MAX_RUNS
        if "--max-runs" in rest:
            i = rest.index("--max-runs")
            try:
                mx = int(rest[i + 1])
            except (IndexError, ValueError):
                mx = MAX_RUNS
        trim(mx)
        return 0
    if cmd == "log":
        if len(rest) < 3:
            return 0  # fail-open: a malformed call never errors the pipeline
        log(rest[0], rest[1], rest[2], **_parse_kv(rest[3:]))
        return 0
    return 0  # unknown subcommand: fail-open


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the full module suite**

Run: `pytest tests/python/test_skillclaw_audit.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Make the script executable and commit**

```bash
chmod +x configs/claude/scripts/skillclaw_audit.py
git add configs/claude/scripts/skillclaw_audit.py tests/python/test_skillclaw_audit.py
git commit -m "feat(skillclaw): audit CLI (log/status/trim) + fail-open hardening"
```

---

## Task 6: Wire `skillclaw_evolve.py` — per-chunk events + live stderr line

**Files:**
- Modify: `configs/claude/scripts/skillclaw_evolve.py`
- Test: `tests/python/test_skillclaw_evolve.py`

The evolver owns all of evolve's audit events: `stage_start` (with chunk count), one `chunk_done` per chunk (carrying cumulative `elapsed_s` so ETA is stateless), and a live stderr progress line. Audit is imported lazily and only when a `run_id` is supplied, so existing callers and tests are untouched.

- [ ] **Step 1: Write the failing test**

Append to `tests/python/test_skillclaw_evolve.py`:

```python
def test_evolve_emits_chunk_events_to_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path / "audit"))
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    big = "x" * 160_000  # ~40k tokens each -> 2 sessions force >=2 chunks at budget 50k
    for i in range(2):
        (sessions_dir / f"s{i}.json").write_text(json.dumps(
            {"session_id": f"s{i}", "turns": [
                {"role": "user", "blocks": [{"kind": "text", "text": big}]}]}))
    template = tmp_path / "tpl.md"
    template.write_text("{{LIBRARY}}{{SESSIONS}}")
    evolved = tmp_path / "evolved"
    out = "~~~skill name=dup\n---\nname: dup\ndescription: d\n---\n# Dup\nstep\n~~~\n"

    ev.evolve(sessions_dir, evolved, template, token_budget=50_000,
              runner=lambda p: out, run_id="20260609T230501Z-4821")

    log_lines = (tmp_path / "audit" / "promote.log").read_text().splitlines()
    events = [json.loads(ln)["event"] for ln in log_lines]
    assert "stage_start" in events
    assert events.count("chunk_done") >= 2
    status = json.loads((tmp_path / "audit" / "status.json").read_text())
    assert status["evolve"]["total"] >= 2
    assert status["evolve"]["chunk"] == status["evolve"]["total"]  # last chunk recorded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/python/test_skillclaw_evolve.py -k chunk_events -v`
Expected: FAIL — `evolve()` rejects the unexpected `run_id` keyword (`TypeError`).

- [ ] **Step 3: Write the implementation**

In `configs/claude/scripts/skillclaw_evolve.py`, add `import sys` is already present and add `import time` near the top imports (after `import subprocess`):

```python
import subprocess
import sys
import time
```

Add a lazy loader and a small formatter after the imports / constants (e.g. after `_SKILL_RE`):

```python
def _load_audit():
    """Import the audit logger lazily; return None if unavailable (fail-open)."""
    try:
        import skillclaw_audit
        return skillclaw_audit
    except Exception:  # noqa: BLE001
        return None


def _fmt_elapsed(s: float) -> str:
    s = int(round(s))
    return "%dm%02ds" % (s // 60, s % 60) if s >= 60 else "%ds" % s
```

Change the `evolve` signature to accept `run_id` and an injectable `audit` module:

```python
def evolve(sessions_dir, evolved_dir, template_path, *,
           committed_dir=None, token_budget=DEFAULT_TOKEN_BUDGET, runner=subprocess_runner,
           run_id=None, audit=None) -> dict:
```

Replace the map loop (the `chunks = chunk_sessions(...)` block through `mapped.extend(parse_candidates(out))`) with:

```python
    chunks = chunk_sessions(sessions, token_budget)
    audit_mod = audit if audit is not None else (_load_audit() if run_id else None)
    if audit_mod and run_id:
        audit_mod.log(run_id, "evolve", "stage_start", chunks=len(chunks))

    mapped: list[dict] = []
    start = time.monotonic()
    for idx, chunk in enumerate(chunks, 1):
        out = runner(build_prompt(template, chunk, library))
        mapped.extend(parse_candidates(out))
        if audit_mod and run_id:
            elapsed = time.monotonic() - start
            _, label = audit_mod.compute_eta(idx, len(chunks), elapsed)
            audit_mod.log(run_id, "evolve", "chunk_done", i=idx, total=len(chunks),
                          chunk_seconds=round(elapsed, 1), elapsed_s=round(elapsed, 1))
            print("[skillclaw] evolve · chunk %d/%d · %s · %s"
                  % (idx, len(chunks), _fmt_elapsed(elapsed), label), file=sys.stderr)
```

Wire the new arg through `main`. In the `argparse` block add:

```python
    ap.add_argument("--run-id", default=None,
                    help="audit run id; enables per-chunk status logging")
```

and pass it in the `evolve(...)` call inside `main`:

```python
        summary = evolve(args.sessions_dir, args.evolved_dir, args.template,
                         committed_dir=args.committed_dir, token_budget=args.token_budget,
                         run_id=args.run_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/python/test_skillclaw_evolve.py -v`
Expected: PASS (existing tests unaffected — they pass no `run_id`, so audit stays off — plus the new chunk-events test).

- [ ] **Step 5: Commit**

```bash
git add configs/claude/scripts/skillclaw_evolve.py tests/python/test_skillclaw_evolve.py
git commit -m "feat(skillclaw): evolve emits per-chunk audit events + live ETA line"
```

---

## Task 7: Wire `skillclaw_promote.sh` — run/stage events, `--status`, trap, trim

**Files:**
- Modify: `configs/claude/scripts/skillclaw_promote.sh`
- Test: `tests/bats/skillclaw_promote.bats`

The orchestrator mints the `run_id`, logs run/stage events through the audit CLI, exposes `--status`, installs a finalization trap so a crash/Ctrl-C records `run_error` + a `failed` status, and trims once per run. Every audit call is best-effort (`|| true`).

- [ ] **Step 1: Write the failing bats tests**

First, in `tests/bats/skillclaw_promote.bats`, extend `setup()` to redirect audit storage into the sandbox. Add these two lines just before the final `: > "$SKILLCLAW_PROMOTE_LOG"`:

```bash
    export SKILLCLAW_AUDIT_DIR="$SANDBOX/skillclaw"
    mkdir -p "$SKILLCLAW_AUDIT_DIR"
```

Then append these tests to the file:

```bash
@test "promote mints a run_id and records it in promote.log" {
    run bash "$SCRIPT" --no-evolve
    assert_success
    run grep -c '"event": "run_start"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    assert_output "1"
    run grep -Eq '"run_id": "[0-9]{8}T[0-9]{6}Z-[0-9]+"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    assert_success
}

@test "--status renders from a seeded status.json" {
    cat > "$SKILLCLAW_AUDIT_DIR/status.json" << 'EOF'
{"run_id":"20260609T230501Z-4821","state":"done","stage":"-",
 "totals":{"ingested":12,"candidates":3,"dropped":0},
 "pr_url":"https://example.test/pr/7","total_seconds":252}
EOF
    run bash "$SCRIPT" --status
    assert_success
    assert_output --partial "done"
    assert_output --partial "3 candidates"
    assert_output --partial "PR https://example.test/pr/7"
}

@test "stage transitions are logged as stage_start events" {
    run bash "$SCRIPT" --no-evolve
    assert_success
    run grep -c '"event": "stage_start"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    [ "$output" -ge 1 ]
}

@test "finalization trap records run_error + failed status on mid-run interrupt" {
    # Make `git switch` fail so --apply dies after run_start/stages -> trap fires.
    cat > "$MOCK_BIN/git" << 'EOF'
#!/usr/bin/env bash
case "$1" in
  rev-parse) echo "abc1234" ;;
  switch) echo "boom" >&2; exit 1 ;;
  *) : ;;
esac
exit 0
EOF
    chmod +x "$MOCK_BIN/git"
    export SKILLCLAW_OPEN_PR=""
    run bash "$SCRIPT" --apply --no-evolve
    assert_failure
    run grep -c '"event": "run_error"' "$SKILLCLAW_AUDIT_DIR/promote.log"
    [ "$output" -ge 1 ]
    run grep -q '"state": "failed"' "$SKILLCLAW_AUDIT_DIR/status.json"
    assert_success
}

@test "unwritable audit path does not abort the run" {
    # Point the audit dir inside a regular file -> every audit call fails open.
    printf 'x' > "$SANDBOX/blocker"
    export SKILLCLAW_AUDIT_DIR="$SANDBOX/blocker/sub"
    run bash "$SCRIPT" --no-evolve
    assert_success
}
```

- [ ] **Step 2: Run the bats suite to verify the new tests fail**

Run: `bats tests/bats/skillclaw_promote.bats`
Expected: the 5 new tests FAIL (no `run_id`/`--status`/audit logging yet); the original tests still pass.

- [ ] **Step 3: Implement the shell changes**

In `configs/claude/scripts/skillclaw_promote.sh`:

(a) After the existing path/env block (just after the `REJECTED=...` / `COMMITTED=...` lines, around line 33), add the audit wiring:

```bash
AUDIT="${SCRIPT_DIR}/skillclaw_audit.py"
# Shared audit storage; evolve.py reads SKILLCLAW_AUDIT_DIR too (default ~/.skillclaw).
export SKILLCLAW_AUDIT_DIR="${SKILLCLAW_AUDIT_DIR:-$HOME/.skillclaw}"
audit() { python3 "$AUDIT" "$@" >/dev/null 2>&1 || true; }
```

(b) Handle `--status` as the first thing in the arg loop (add a new case before `--apply`):

```bash
        --status) python3 "$AUDIT" status; exit 0 ;;
```

(c) After argument parsing completes (after the `done` of the `while` loop at line 51) and before the idempotency check, mint the run id, install the trap, and log `run_start`:

```bash
run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
RUN_DONE=false
CUR_STAGE="startup"
finalize() {
    local ec=$?
    if [[ "$RUN_DONE" != true ]]; then
        audit log "$run_id" "$CUR_STAGE" run_error message="exit ${ec}"
    fi
}
trap finalize EXIT
audit log "$run_id" "-" run_start window_days=0 token_budget=0 apply="$APPLY"
```

(d) Wrap each pipeline stage with `CUR_STAGE` + `stage_start`/`stage_end`. Replace the ingest block (lines 70-74) with:

```bash
# 1. Ingest transcripts → sessions (passive; no proxy).
if [[ "$DO_EVOLVE" == true ]]; then
    CUR_STAGE="ingest"; _t0=$SECONDS
    echo "▸ ingest…"
    audit log "$run_id" ingest stage_start
    python3 "$INGEST" "$TRANSCRIPTS" "$SESSIONS" --state "$STATE" >/dev/null 2>&1 \
        || err "ingest returned non-zero (continuing)"
    audit log "$run_id" ingest stage_end seconds=$((SECONDS - _t0))
fi
```

Replace the scrub block (lines 76-79) with:

```bash
# 2. Scrub captured sessions (best-effort; never blocks).
if [[ -d "$SESSIONS" ]]; then
    CUR_STAGE="scrub"; _t0=$SECONDS
    echo "▸ scrub…"
    audit log "$run_id" scrub stage_start
    python3 "${SCRIPT_DIR}/skillclaw_scrub.py" "$SESSIONS" >/dev/null 2>&1 || true
    audit log "$run_id" scrub stage_end seconds=$((SECONDS - _t0))
fi
```

Replace the evolve block (lines 81-87) with (passing `--run-id`; evolve owns its own stage events):

```bash
# 3. Evolve (skip with --no-evolve). evolve.py logs its own stage_start/chunk_done.
if [[ "$DO_EVOLVE" == true ]]; then
    CUR_STAGE="evolve"
    echo "▸ evolve…"
    python3 "$EVOLVE" "$SESSIONS" "$EVOLVED" --template "$TEMPLATE" \
        --committed-dir "$COMMITTED" --run-id "$run_id" >/dev/null \
        || err "evolve returned non-zero (continuing)"
fi
```

Set the stage before classify. Immediately before the `classify_args=(...)` line (line 91), add:

```bash
CUR_STAGE="classify"; echo "▸ classify…"
audit log "$run_id" classify stage_start
```

(e) Log the `candidates` event after the diff table is computed. Immediately after the `promote_names=...` line (line 115), add:

```bash
# Structured candidate record (names only — never session content).
new_json="$(echo "$classify_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([c["name"] for c in d.get("promote",[]) if c.get("status")=="NEW"]))')"
changed_json="$(echo "$classify_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([c["name"] for c in d.get("promote",[]) if c.get("status")=="CHANGED"]))')"
dropped_json="$(echo "$classify_json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps([c["name"] for c in d.get("dropped",[])]))')"
audit log "$run_id" classify candidates new="$new_json" changed="$changed_json" dropped="$dropped_json"
```

(f) Finalize on the two early non-error exits. Replace the "Nothing to promote." block (lines 117-120) with:

```bash
if [[ -z "$promote_names" ]]; then
    echo "Nothing to promote."
    RUN_DONE=true
    audit log "$run_id" "-" run_end state=done total_seconds=$SECONDS
    exit 0
fi
```

Replace the dry-run block (lines 122-126) with:

```bash
if [[ "$APPLY" != true ]]; then
    echo ""
    echo "Dry run — re-run with --apply to open a review PR."
    RUN_DONE=true
    audit log "$run_id" "-" run_end state=done total_seconds=$SECONDS
    exit 0
fi
```

(g) Set the promote stage and log `pr_opened` + final `run_end`. Immediately before the `count=...` line (line 129) add:

```bash
CUR_STAGE="promote"; echo "▸ promote…"
audit log "$run_id" promote stage_start
```

Replace the final two lines (lines 153-154, `echo "Opened review PR: $pr_url"`) with:

```bash
audit log "$run_id" promote pr_opened url="$pr_url"
echo "Opened review PR: $pr_url"
RUN_DONE=true
audit log "$run_id" "-" run_end state=done total_seconds=$SECONDS
audit trim
```

- [ ] **Step 4: Run the bats suite to verify it passes**

Run: `bats tests/bats/skillclaw_promote.bats`
Expected: PASS (all original + 5 new tests).

- [ ] **Step 5: shellcheck the script**

Run: `shellcheck configs/claude/scripts/skillclaw_promote.sh`
Expected: clean (no warnings). The `_t0`/`CUR_STAGE`/`run_id` vars are used; `audit()` is a real function.

- [ ] **Step 6: Commit**

```bash
git add configs/claude/scripts/skillclaw_promote.sh tests/bats/skillclaw_promote.bats
git commit -m "feat(skillclaw): promote.sh audit events, --status, finalization trap"
```

---

## Task 8: Documentation + full-suite verification

**Files:**
- Modify: `docs/SKILLCLAW.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Document the audit log in `docs/SKILLCLAW.md`**

Insert a new section immediately before `## Security` (currently line 76):

```markdown
## Audit log + live status

Each `skillclaw_promote` run writes two best-effort artifacts under `~/.skillclaw/`
(fail-open — audit I/O never aborts or delays a run):

- **`promote.log`** — append-only JSONL audit history (one event per line:
  `run_start`, `stage_start`/`stage_end`, `chunk_done`, `candidates`, `pr_opened`,
  `run_end`/`run_error`). Self-trims to the most recent ~50 runs.
- **`status.json`** — overwritten snapshot of the current/last run plus a rough,
  explicitly-labeled ETA (only the evolve stage predicts, and only once ≥2 chunks
  complete; before that it shows `estimating…`).

During a run the evolve stage prints a live per-chunk line to stderr, e.g.
`[skillclaw] evolve · chunk 4/12 · 1m00s · ~2m left (est)`.

Query the latest run at any time:

```bash
skillclaw_promote.sh --status
# run 20260609T2305 · evolve · chunk 4/12 · 1m00s elapsed · ~2m left (est)
# last run: done · 3 candidates · PR https://…/pull/7 · 4m12s
# no recent run
```

The log records counts, names, timings, and URLs only — never session content
(evolve inputs are already scrubbed upstream).
```

- [ ] **Step 2: Add a CHANGELOG entry**

Under the `## [Unreleased]` heading in `CHANGELOG.md`, add:

```markdown
## [Unreleased]

### Added
- **SkillClaw promote audit log + live status/ETA** — new `skillclaw_audit.py`
  writes an append-only `~/.skillclaw/promote.log` (JSONL history, self-trimmed to
  ~50 runs) and a live `status.json` snapshot. `skillclaw_promote.sh --status`
  reports where a run is and a rough ETA; the evolve stage prints per-chunk
  progress. Fail-open: audit I/O never blocks a promote run.
```

- [ ] **Step 3: Run the full affected suite**

Run:

```bash
pytest tests/python/test_skillclaw_audit.py tests/python/test_skillclaw_evolve.py -v
bats tests/bats/skillclaw_promote.bats
shellcheck configs/claude/scripts/skillclaw_promote.sh
```

Expected: all green; shellcheck clean.

- [ ] **Step 4: Verify the audit log + status.json are valid JSON end-to-end**

Run (uses a throwaway audit dir so it never touches the real `~/.skillclaw`):

```bash
SKILLCLAW_AUDIT_DIR=$(mktemp -d) python3 - <<'PY'
import os, json, subprocess, sys
sys.path.insert(0, "configs/claude/scripts")
import skillclaw_audit as a
rid = "20260609T230501Z-4821"
a.log(rid, "-", "run_start", window_days=30, token_budget=100000, apply=True)
a.log(rid, "evolve", "stage_start", chunks=3)
a.log(rid, "evolve", "chunk_done", i=2, total=3, chunk_seconds=10.0, elapsed_s=20.0)
a.log(rid, "-", "run_end", state="done", total_seconds=42.0)
d = os.environ["SKILLCLAW_AUDIT_DIR"]
for ln in open(f"{d}/promote.log"):
    json.loads(ln)                      # raises if any line is invalid JSON
json.load(open(f"{d}/status.json"))     # raises if status is invalid JSON
print("OK:", a.render_status())
PY
```

Expected: `OK: last run: done · ... · 42s` and no JSON errors.

- [ ] **Step 5: Commit**

```bash
git add docs/SKILLCLAW.md CHANGELOG.md
git commit -m "docs(skillclaw): document promote audit log + --status"
```

---

## Self-Review Notes

- **Spec coverage:** two artifacts (Tasks 2/4), `--status` both surfaces (Tasks 5/7), ETA-always-progress-once-measurable (Tasks 1/2/6), retention ~50 (Task 4), fail-open (Tasks 2-5,7), stale-pid liveness (Task 3), finalization trap (Task 7), no-state-bleed reset (Task 2), atomic trim & status writes (Tasks 1/4), storage auto-init (Task 5), `${SCRIPT_DIR}`-relative invocation (Task 7), cumulative `elapsed_s` for stateless ETA (Task 6), secrets posture = names/counts only (Tasks 7/8). All design decisions and all 7 `agy` findings are mapped to tasks.
- **Type consistency:** `compute_eta(chunks_done, chunks_total, elapsed_s)`, `log(run_id, stage, event, **fields)`, `render_status()`, `trim(max_runs=50)`, and `evolve(..., run_id=None, audit=None)` are referenced identically across every task and test.
- **Non-goals respected:** no `--history`, no external metrics/OTel, no change to pipeline behavior — observability only.
