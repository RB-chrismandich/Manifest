"""Foundational + US4 — run persistence, audit, report (T007/T032, FR-010)."""

import json
import re
import stat

from cddl.persistence import RunStore, new_run_id, repo_slug


def test_run_id_format():
    rid = new_run_id()
    assert re.fullmatch(r"\d{8}T\d{6}Z-[a-z0-9]{4}", rid)


def test_repo_slug_stable_and_safe(tmp_path):
    repo = tmp_path / "My Repo!"
    repo.mkdir()
    slug = repo_slug(repo)
    assert slug == repo_slug(repo)  # deterministic
    assert re.fullmatch(r"[A-Za-z0-9._-]+", slug)
    other = tmp_path / "other"
    other.mkdir()
    assert slug != repo_slug(other)  # distinct repos, distinct slugs


def test_run_dir_created_chmod_700(state_root, fixture_repo):
    store = RunStore(state_root, fixture_repo).create()
    assert store.run_dir.is_dir()
    mode = stat.S_IMODE(store.run_dir.stat().st_mode)
    assert mode == 0o700
    assert (store.run_dir / "iterations").is_dir()
    assert store.run_dir.parent == state_root / "cddl" / "runs" / store.slug


def test_state_json_atomic_rewrite(state_root, fixture_repo):
    store = RunStore(state_root, fixture_repo).create()
    store.write_state({"phase": "clarify", "status": "running"})
    store.write_state({"phase": "implement", "status": "running"})
    state = store.read_state()
    assert state["phase"] == "implement"
    leftovers = [p for p in store.run_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_latest_run_lookup(state_root, fixture_repo):
    first = RunStore(state_root, fixture_repo, run_id="20260101T000000Z-aaaa").create()
    second = RunStore(state_root, fixture_repo, run_id="20260202T000000Z-bbbb").create()
    first.write_state({"status": "success"})
    second.write_state({"status": "running"})
    latest = RunStore.latest(state_root, fixture_repo)
    assert latest is not None
    assert latest.run_id == second.run_id


def test_audit_fail_open_when_writer_missing(
    state_root, fixture_repo, monkeypatch, capsys
):
    import cddl.persistence as persistence

    monkeypatch.setattr(
        persistence, "AUDIT_SCRIPT", state_root / "nope" / "audit_log.sh"
    )
    store = RunStore(state_root, fixture_repo).create()
    store.audit("run_started")  # must not raise (FR-010 fail-open)


def test_audit_writes_via_stubbed_writer(
    state_root, fixture_repo, monkeypatch, tmp_path
):
    import cddl.persistence as persistence

    stub = tmp_path / "audit_log.sh"
    out = tmp_path / "audit.jsonl"
    stub.write_text(
        '#!/usr/bin/env bash\n[ "$1" = append ] || exit 0\n'
        f'printf \'%s\\n\' "$2" >> "{out}"\n'
    )
    stub.chmod(0o755)
    monkeypatch.setattr(persistence, "AUDIT_SCRIPT", stub)
    monkeypatch.setenv("CDDL_AUDIT_FILE", str(out))
    store = RunStore(state_root, fixture_repo).create()
    store.audit("run_started", status="running")
    record = json.loads(out.read_text().splitlines()[0])
    assert record["event"] == "run_started"
    assert record["run_id"] == store.run_id
    assert record["component"] == "cddl"


def test_audit_env_mapped_to_audit_log_file_env(
    state_root, fixture_repo, monkeypatch, tmp_path
):
    """CDDL_AUDIT_FILE must reach audit_log.sh as its generic AUDIT_LOG_FILE."""
    import cddl.persistence as persistence

    stub = tmp_path / "audit_log.sh"
    envdump = tmp_path / "env.txt"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'printf \'%s\\n\' "${{AUDIT_LOG_FILE:-unset}}" > "{envdump}"\n'
    )
    stub.chmod(0o755)
    monkeypatch.setattr(persistence, "AUDIT_SCRIPT", stub)
    monkeypatch.setenv("CDDL_AUDIT_FILE", "/custom/audit.jsonl")
    RunStore(state_root, fixture_repo).create().audit("x")
    assert envdump.read_text().strip() == "/custom/audit.jsonl"


def test_write_text_creates_parents(state_root, fixture_repo):
    store = RunStore(state_root, fixture_repo).create()
    p = store.write_text("iterations/1/candidate.md", "raw output\n")
    assert p.read_text() == "raw output\n"
