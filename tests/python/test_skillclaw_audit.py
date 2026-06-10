from pathlib import Path
import json
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
