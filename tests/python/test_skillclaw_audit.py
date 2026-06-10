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
