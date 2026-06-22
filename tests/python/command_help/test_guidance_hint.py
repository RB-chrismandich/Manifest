"""T016 — failing-first tests for guidance_hint.py (spec 362, US2).

Moment→command mapping, ref resolution against the catalog, dedup by dedup_key,
priority ordering, and one-shot emission. US3 (T022) extends this file with
preference-gating and rate-limit tests. Written before the implementation.
"""
from pathlib import Path
import sys

import pytest

sys.path.insert(
    0, str(Path(__file__).resolve().parents[3] / "configs/claude/scripts")
)
import guidance_hint as gh  # noqa: E402


CATALOG_NAMES = {"verify", "project-commit", "checkpoint", "pr-review"}

REGISTRY = {
    "moments": [
        {"id": "pre-commit", "trigger": "PreToolUse:git-commit", "description": "commit"},
        {"id": "pr-open", "trigger": "PreToolUse:pr-create", "description": "pr"},
        {"id": "high-context", "trigger": "context-high", "description": "ctx"},
    ],
    "rules": [
        {"moment_id": "pre-commit", "command_refs": ["verify", "project-commit"],
         "message": "Before committing: /verify or /project-commit.",
         "priority": 10, "dedup_key": "commit-guidance", "category": "hint"},
        {"moment_id": "pre-commit", "command_refs": ["verify"],
         "message": "Lower-priority dup.",
         "priority": 1, "dedup_key": "commit-guidance", "category": "hint"},
        {"moment_id": "high-context", "command_refs": ["checkpoint"],
         "message": "Context is high — consider /checkpoint.",
         "priority": 10, "dedup_key": "context-guidance", "category": "reminder",
         "rate_limit": "30m"},
    ],
}


# --- moment detection ------------------------------------------------------- #
def test_detect_pre_commit_from_git_commit():
    assert gh.detect_moment(REGISTRY, "git commit -m 'wip'") == "pre-commit"


def test_detect_pr_open_from_gh_pr_create():
    assert gh.detect_moment(REGISTRY, "gh pr create --fill") == "pr-open"


def test_unrelated_command_detects_nothing():
    assert gh.detect_moment(REGISTRY, "ls -la") is None
    assert gh.detect_moment(REGISTRY, "echo git committed yesterday") is None


# --- selection: dedup + priority -------------------------------------------- #
def test_select_dedups_by_key_keeping_highest_priority():
    hints = gh.select_hints(REGISTRY, "pre-commit")
    assert len(hints) == 1
    assert hints[0]["message"].startswith("Before committing")


def test_select_orders_by_priority_desc():
    reg = {
        "moments": REGISTRY["moments"],
        "rules": [
            {"moment_id": "pre-commit", "command_refs": ["verify"], "message": "low",
             "priority": 1, "dedup_key": "a", "category": "hint"},
            {"moment_id": "pre-commit", "command_refs": ["project-commit"], "message": "high",
             "priority": 9, "dedup_key": "b", "category": "hint"},
        ],
    }
    msgs = [h["message"] for h in gh.select_hints(reg, "pre-commit")]
    assert msgs == ["high", "low"]


def test_select_unknown_moment_returns_empty():
    assert gh.select_hints(REGISTRY, "nope") == []


# --- registry validation ---------------------------------------------------- #
def test_validate_passes_for_good_registry():
    gh.validate_registry(REGISTRY, CATALOG_NAMES)  # no raise


def test_validate_dangling_command_ref_raises():
    reg = {
        "moments": REGISTRY["moments"],
        "rules": [{"moment_id": "pre-commit", "command_refs": ["does-not-exist"],
                   "message": "x", "priority": 1, "dedup_key": "k", "category": "hint"}],
    }
    with pytest.raises(gh.RegistryError):
        gh.validate_registry(reg, CATALOG_NAMES)


def test_validate_unknown_moment_ref_raises():
    reg = {
        "moments": REGISTRY["moments"],
        "rules": [{"moment_id": "ghost", "command_refs": ["verify"],
                   "message": "x", "priority": 1, "dedup_key": "k", "category": "hint"}],
    }
    with pytest.raises(gh.RegistryError):
        gh.validate_registry(reg, CATALOG_NAMES)


def test_validate_reminder_without_rate_limit_raises():
    reg = {
        "moments": REGISTRY["moments"],
        "rules": [{"moment_id": "high-context", "command_refs": ["checkpoint"],
                   "message": "x", "priority": 1, "dedup_key": "k", "category": "reminder"}],
    }
    with pytest.raises(gh.RegistryError):
        gh.validate_registry(reg, CATALOG_NAMES)


def test_validate_reminder_with_unparseable_rate_limit_raises():
    # Regression (review finding): '30min' passes a presence check but parses to
    # None at runtime, silently disabling the rate limit. Validation must reject it.
    reg = {
        "moments": REGISTRY["moments"],
        "rules": [{"moment_id": "high-context", "command_refs": ["checkpoint"],
                   "message": "x", "priority": 1, "dedup_key": "k",
                   "category": "reminder", "rate_limit": "30min"}],
    }
    with pytest.raises(gh.RegistryError):
        gh.validate_registry(reg, CATALOG_NAMES)


def test_validate_missing_moment_id_raises_registry_error_not_keyerror():
    reg = {"moments": REGISTRY["moments"],
           "rules": [{"command_refs": ["verify"], "message": "x", "priority": 1,
                      "dedup_key": "k", "category": "hint"}]}
    with pytest.raises(gh.RegistryError):
        gh.validate_registry(reg, CATALOG_NAMES)


# --- one-shot formatting ---------------------------------------------------- #
def test_format_hints_one_shot_text():
    hints = gh.select_hints(REGISTRY, "pre-commit")
    out = gh.format_hints(hints)
    assert "/verify" in out
    assert out.count("\n") <= 1  # one-shot, compact


# --- the real shipped registry validates against the real catalog ----------- #
def test_real_registry_validates_against_real_catalog():
    import command_catalog as cc
    registry = gh.load_registry(gh.DEFAULT_REGISTRY)
    names = {c["name"] for c in cc.build_catalog()["commands"]}
    gh.validate_registry(registry, names)


# =========================================================================== #
# T022 — US3: preference gating, merge order, rate-limit, single-opt-out
# =========================================================================== #
from datetime import datetime, timedelta, timezone  # noqa: E402

NOW = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)

HINT_RULE = {"moment_id": "pre-commit", "command_refs": ["verify"], "message": "hint msg",
             "priority": 10, "dedup_key": "k", "category": "hint"}
REMINDER_RULE = {"moment_id": "high-context", "command_refs": ["checkpoint"],
                 "message": "reminder msg", "priority": 10, "dedup_key": "r",
                 "category": "reminder", "rate_limit": "30m"}


def all_on():
    return {"enabled": True,
            "categories": {"hints": True, "reminders": True, "discovery": True},
            "verbosity": "normal", "rate_limit": {}}


# --- global + per-category gating ------------------------------------------- #
def test_global_disable_suppresses_everything():
    prefs = all_on(); prefs["enabled"] = False
    assert gh.apply_gating([HINT_RULE, REMINDER_RULE], prefs, "pre-commit", {}, NOW) == []


def test_disabling_reminders_keeps_hints():
    prefs = all_on(); prefs["categories"]["reminders"] = False
    hints = gh.apply_gating([HINT_RULE], prefs, "pre-commit", {}, NOW)
    reminders = gh.apply_gating([REMINDER_RULE], prefs, "high-context", {}, NOW)
    assert [h["message"] for h in hints] == ["hint msg"]
    assert reminders == []


def test_disabling_hints_keeps_reminders():
    prefs = all_on(); prefs["categories"]["hints"] = False
    assert gh.apply_gating([HINT_RULE], prefs, "pre-commit", {}, NOW) == []
    assert len(gh.apply_gating([REMINDER_RULE], prefs, "high-context", {}, NOW)) == 1


# --- verbosity gating ------------------------------------------------------- #
def test_verbose_level_rule_hidden_at_normal_shown_at_verbose():
    verbose_rule = {**HINT_RULE, "level": "verbose"}
    normal = all_on()
    verbose = {**all_on(), "verbosity": "verbose"}
    assert gh.apply_gating([verbose_rule], normal, "pre-commit", {}, NOW) == []
    assert len(gh.apply_gating([verbose_rule], verbose, "pre-commit", {}, NOW)) == 1


def test_quiet_hides_normal_level_rule():
    quiet = {**all_on(), "verbosity": "quiet"}
    assert gh.apply_gating([HINT_RULE], quiet, "pre-commit", {}, NOW) == []


# --- rate-limit window ------------------------------------------------------ #
def test_reminder_within_window_suppressed():
    last = {"high-context": NOW - timedelta(minutes=10)}  # 10m ago, window 30m
    assert gh.apply_gating([REMINDER_RULE], all_on(), "high-context", last, NOW) == []


def test_reminder_after_window_allowed():
    last = {"high-context": NOW - timedelta(minutes=40)}  # 40m ago > 30m window
    assert len(gh.apply_gating([REMINDER_RULE], all_on(), "high-context", last, NOW)) == 1


def test_reminder_never_fired_allowed():
    assert len(gh.apply_gating([REMINDER_RULE], all_on(), "high-context", {}, NOW)) == 1


# --- preference merge order (defaults ← local override) --------------------- #
def test_load_preferences_local_overrides_default(tmp_path):
    shipped = tmp_path / "guidance.yml"
    shipped.write_text(
        "enabled: true\ncategories: {hints: true, reminders: true, discovery: true}\n"
        "verbosity: normal\n", encoding="utf-8")
    local = tmp_path / "guidance_local.yml"
    local.write_text("categories: {reminders: false}\n", encoding="utf-8")
    prefs = gh.load_preferences(str(shipped), str(local))
    assert prefs["categories"]["reminders"] is False     # local wins
    assert prefs["categories"]["hints"] is True           # default preserved
    assert prefs["enabled"] is True


def test_load_preferences_absent_local_is_all_defaults(tmp_path):
    shipped = tmp_path / "guidance.yml"
    shipped.write_text("enabled: true\ncategories: {hints: true, reminders: true}\n",
                       encoding="utf-8")
    prefs = gh.load_preferences(str(shipped), str(tmp_path / "absent.yml"))
    assert prefs["categories"]["reminders"] is True


# --- SC-004: a single opt-out write yields zero subsequent ------------------ #
def test_single_opt_out_write_then_suppressed(tmp_path):
    shipped = tmp_path / "guidance.yml"
    shipped.write_text(
        "enabled: true\ncategories: {hints: true, reminders: true, discovery: true}\n"
        "verbosity: normal\n", encoding="utf-8")
    local = tmp_path / "guidance_local.yml"
    assert not local.exists()
    gh.set_local_pref(str(local), "categories.reminders", False)  # the one opt-out
    assert local.exists()                                          # lazily created
    prefs = gh.load_preferences(str(shipped), str(local))
    assert gh.apply_gating([REMINDER_RULE], prefs, "high-context", {}, NOW) == []
    # and it never dirtied the shipped/tracked file
    assert "reminders: true" in shipped.read_text()


# =========================================================================== #
# T033 — SC-003 measurement harness: over the registered Workflow Moments +
# a fixed unrelated-action sample, assert a relevant command surfaces for ≥90%
# of moments and a hint fires on ≤5% of unrelated actions.
# =========================================================================== #
# Representative command text for each detection-based moment (high-context is a
# signal, exercised via the explicit-moment path).
MOMENT_SAMPLES = {
    "pre-commit": "git commit -m 'wip'",
    "pr-open": "gh pr create --fill",
    "refactor-start": "/refactor-python src/",
    "high-context": None,  # signal-only
}

UNRELATED_ACTIONS = [
    "ls -la", "cat README.md", "echo hello", "git status", "git diff",
    "npm test", "python3 foo.py", "grep -r TODO .", "mkdir build", "cd src",
    "pytest -q", "docker ps", "curl https://example.com", "git log --oneline",
    "rm -rf build", "sed -n '1,5p' f", "git add .", "make", "node app.js",
    "git push",
]


def _real_registry():
    return gh.load_registry(gh.DEFAULT_REGISTRY)


def test_sc003_moment_coverage_at_least_90_percent():
    registry = _real_registry()
    moment_ids = [m["id"] for m in registry["moments"]]
    surfaced = 0
    for mid in moment_ids:
        # detection check for command-based moments
        sample = MOMENT_SAMPLES.get(mid)
        if sample is not None:
            assert gh.detect_moment(registry, sample) == mid, mid
        # the registry must surface ≥1 relevant command for this moment
        hints = gh.select_hints(registry, mid)
        if hints and all(h.get("command_refs") for h in hints):
            surfaced += 1
    coverage = surfaced / len(moment_ids)
    assert coverage >= 0.90, f"moment coverage {coverage:.0%} < 90%"


def test_sc003_false_positive_rate_at_most_5_percent():
    registry = _real_registry()
    false_positives = sum(
        1 for cmd in UNRELATED_ACTIONS if gh.detect_moment(registry, cmd) is not None
    )
    rate = false_positives / len(UNRELATED_ACTIONS)
    assert rate <= 0.05, f"false-positive rate {rate:.0%} > 5% ({false_positives} hits)"


# --- regression: naive last_fired timestamp must not break the rate limit ---- #
def test_load_last_fired_coerces_naive_timestamp_to_utc(tmp_path, monkeypatch):
    state = tmp_path / "guidance"
    state.mkdir()
    # A naive ISO timestamp (no offset) — as older code or a hand edit might write.
    (state / "last_fired.json").write_text(
        '{"high-context": "2026-06-21T11:50:00"}', encoding="utf-8")
    monkeypatch.setenv("GUIDANCE_STATE_DIR", str(state))
    loaded = gh.load_last_fired()
    assert loaded["high-context"].tzinfo is not None       # coerced to aware
    # and it now participates in the window math without raising
    suppressed = gh.apply_gating([REMINDER_RULE], all_on(), "high-context", loaded, NOW)
    assert suppressed == []                                  # 10m ago < 30m window
