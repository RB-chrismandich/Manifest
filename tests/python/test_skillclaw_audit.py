import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "configs/claude/scripts"))
import skillclaw_audit as audit


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


def test_compute_eta_sub_minute_rounds_up_to_one_minute():
    # 3 of 4 chunks done in 4s -> eta 1.33s, intentionally labelled ~1m (rough).
    eta_s, label = audit.compute_eta(3, 4, 4)
    assert eta_s < 60
    assert label == "~1m left (est)"


def test_compute_eta_non_numeric_inputs_estimate_safely():
    assert audit.compute_eta(None, 12, 60) == (None, "estimating…")
    assert audit.compute_eta(4, "twelve", 60) == (None, "estimating…")


def _read(p):
    return json.loads(Path(p).read_text())


def test_log_appends_jsonl_and_updates_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    audit.log(
        "20260609T230501Z-4821",
        "-",
        "run_start",
        window_days=30,
        token_budget=100000,
        apply=True,
    )
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
    audit.log(
        rid, "evolve", "chunk_done", i=4, total=12, chunk_seconds=15.0, elapsed_s=60
    )
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
    assert status["pr_url"] is None  # prior run's PR must not bleed in
    assert status["state"] == "running"


def test_stage_end_ingested_recorded(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(rid, "ingest", "stage_end", ingested=12, seconds=3)
    assert _read(tmp_path / "status.json")["totals"]["ingested"] == 12


def test_candidates_counts_new_changed_and_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(
        rid,
        "classify",
        "candidates",
        new=["a", "b"],
        changed=["c"],
        dropped=[{"name": "d", "reason": "x"}],
    )
    totals = _read(tmp_path / "status.json")["totals"]
    assert totals["candidates"] == 3  # 2 new + 1 changed
    assert totals["dropped"] == 1


def test_pr_opened_sets_pr_url(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(rid, "promote", "pr_opened", url="https://x/pull/7")
    assert _read(tmp_path / "status.json")["pr_url"] == "https://x/pull/7"


def test_run_end_sets_state_and_total_seconds(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(rid, "-", "run_end", state="done", total_seconds=252.4)
    st = _read(tmp_path / "status.json")
    assert st["state"] == "done" and st["total_seconds"] == 252.4


def test_run_error_sets_failed_state_and_stage(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(rid, "evolve", "run_error", message="boom")
    st = _read(tmp_path / "status.json")
    assert st["state"] == "failed" and st["error_stage"] == "evolve"


def test_render_status_no_recent_run(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    assert audit.render_status() == "no recent run"


def test_render_status_running_evolve(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    monkeypatch.setattr(audit, "_pid_alive", lambda pid: True)
    rid = "20260609T230501Z-4821"
    audit.log(rid, "-", "run_start")
    audit.log(rid, "evolve", "stage_start", chunks=12)
    audit.log(
        rid, "evolve", "chunk_done", i=4, total=12, chunk_seconds=15.0, elapsed_s=60
    )
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
    audit.log(
        rid, "classify", "candidates", new=["a", "b", "c"], changed=[], dropped=[]
    )
    audit.log(rid, "promote", "pr_opened", url="https://x/pull/7")
    audit.log(rid, "-", "run_end", state="done", total_seconds=252.4)
    out = audit.render_status()
    assert "done" in out and "3 candidates" in out and "PR https://x/pull/7" in out


def test_fmt_secs_negative_is_unknown():
    assert audit._fmt_secs(-5) == "?"
    assert audit._fmt_secs(None) == "?"


def test_render_status_unknown_state_is_not_mislabeled_done(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    (tmp_path / "status.json").write_text('{"run_id": "r-1", "state": "aborted"}')
    assert audit.render_status() == "no recent run"


def test_trim_keeps_only_recent_run_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    for i in range(5):
        audit.log(f"run-{i}", "-", "run_start")
    audit.trim(max_runs=2)
    rids = {
        json.loads(ln)["run_id"]
        for ln in (tmp_path / "promote.log").read_text().splitlines()
    }
    assert rids == {"run-3", "run-4"}


def test_trim_clamps_nonpositive_max_runs_to_keep_recent_one(tmp_path, monkeypatch):
    # max_runs <= 0 must not retain everything (order[-0:] == all); it clamps to 1.
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    for i in range(3):
        audit.log(f"run-{i}", "-", "run_start")
    audit.trim(max_runs=0)
    rids = {
        json.loads(ln)["run_id"]
        for ln in (tmp_path / "promote.log").read_text().splitlines()
    }
    assert rids == {"run-2"}


def test_trim_survives_valid_json_non_dict_lines(tmp_path, monkeypatch):
    """Issue #311: a torn write leaving `123` or `null` (valid JSON, not a dict)
    raised AttributeError into the outer fail-open handler, permanently
    disabling trimming."""
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    for i in range(4):
        audit.log(f"run-{i}", "-", "run_start")
    log = tmp_path / "promote.log"
    log.write_text(log.read_text() + "123\nnull\nnot json at all\n")
    audit.trim(max_runs=2)
    lines = log.read_text().splitlines()
    rids = {json.loads(ln)["run_id"] for ln in lines}
    assert rids == {"run-2", "run-3"}  # trim actually ran
    assert "123" not in lines and "null" not in lines


def test_trim_is_atomic_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    for i in range(3):
        audit.log(f"run-{i}", "-", "run_start")
    original = (tmp_path / "promote.log").read_text()

    def boom(*a, **k):
        raise OSError("simulated mid-trim crash")

    monkeypatch.setattr(audit.os, "replace", boom)
    audit.trim(max_runs=1)  # fail-open: swallows the error
    assert (tmp_path / "promote.log").read_text() == original  # untouched


def test_fail_open_on_unwritable_dir(tmp_path, monkeypatch):
    # Point the audit dir *inside* a regular file so mkdir raises NotADirectoryError.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a dir")
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(blocker / "sub"))
    audit.log("run-x", "-", "run_start")  # must not raise
    assert audit.render_status() == "no recent run"


def test_storage_auto_inits_when_absent(tmp_path, monkeypatch):
    target = tmp_path / "fresh" / "nested"  # does not exist yet
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(target))
    audit.log("run-1", "-", "run_start")
    assert (target / "promote.log").exists()
    assert (target / "status.json").exists()


def test_storage_auto_init_chmods_dir_700(tmp_path, monkeypatch):
    # _ensure_storage() is the Tier-1 honeypot guard: "a fresh install never
    # silently logs nothing" must also mean it never logs into a
    # world/group-readable directory. chmod is an explicit os.chmod() call
    # (not umask-derived), so this holds under any default umask, incl. root.
    target = tmp_path / "fresh" / "nested"
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(target))
    audit.log("run-1", "-", "run_start")
    assert oct(target.stat().st_mode)[-3:] == "700"


def test_ensure_storage_chmod_is_fail_open_not_a_noop(tmp_path, monkeypatch):
    # os.chmod is wrapped in contextlib.suppress(OSError) so a chmod failure
    # (e.g. a filesystem without POSIX perms) degrades silently rather than
    # aborting the run — but confirm it's a genuine best-effort *attempt*,
    # not code that was silently deleted, by observing it actually applies
    # 700 when the syscall does succeed (asserted above) and never raises
    # even when os.chmod is made to fail.
    target = tmp_path / "raises"
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(target))

    def _boom(*_a, **_kw):
        raise OSError("simulated chmod failure")

    monkeypatch.setattr(audit.os, "chmod", _boom)
    audit.log("run-1", "-", "run_start")  # must not raise despite chmod boom
    assert (target / "promote.log").exists()


def test_cli_log_parses_key_value_and_json(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rc = audit.main(
        [
            "log",
            "run-1",
            "classify",
            "candidates",
            'new=["a","b"]',
            "dropped=[]",
            "changed=[]",
        ]
    )
    assert rc == 0
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["totals"]["candidates"] == 2


def test_cli_status_and_trim(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    assert audit.main(["status"]) == 0
    assert capsys.readouterr().out.strip() == "no recent run"
    assert audit.main(["trim", "--max-runs", "10"]) == 0  # no log yet -> no-op, rc 0


def test_cli_log_bare_key_is_silently_dropped(tmp_path, monkeypatch):
    # A field passed without `=` (e.g. `apply` instead of `apply=true`) is dropped,
    # never raised — the shell must never get a nonzero from a typo'd audit call.
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rc = audit.main(["log", "run-1", "-", "run_start", "apply", "window_days=30"])
    assert rc == 0
    status = json.loads((tmp_path / "status.json").read_text())
    assert status.get("config", {}).get("window_days") == 30  # good pair kept
    assert "apply" not in status.get("config", {})  # bare key dropped


def test_cli_trim_non_int_max_runs_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    for i in range(3):
        audit.log(f"run-{i}", "-", "run_start")
    rc = audit.main(["trim", "--max-runs", "notanint"])  # bad value -> default
    assert rc == 0
    rids = {
        json.loads(ln)["run_id"]
        for ln in (tmp_path / "promote.log").read_text().splitlines()
    }
    assert rids == {"run-0", "run-1", "run-2"}  # default 50 keeps all


def test_cli_log_with_too_few_args_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("SKILLCLAW_AUDIT_DIR", str(tmp_path))
    rc = audit.main(["log", "run-1"])  # <3 positional -> no-op
    assert rc == 0
    assert not (tmp_path / "promote.log").exists()  # nothing written
