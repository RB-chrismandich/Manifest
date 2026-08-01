"""hook_dispatch.py — resolving the unified-hook + handler at fire-time.

Skill storage has moved three times in ~5 weeks (bootstrap copy ->
apm-managed ~/.manifest/skills -> plugin bundles, PR #685), and each move
broke the absolute path baked into settings.json's PreToolUse hook, blocking
every Bash tool call until someone noticed. The distinction that matters here
is fail-open vs fail-closed: a hook that can't resolve its own target must
allow the tool call through, never block it.
"""

import importlib.util
import json
import pathlib
import subprocess
import sys

SCRIPT = (
    pathlib.Path(__file__).resolve().parents[2]
    / "configs/claude/scripts/hook_dispatch.py"
)
_spec = importlib.util.spec_from_file_location("hook_dispatch", SCRIPT)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _make_cached_skill(cache_root, bundle_skill, version, rel_path, content=""):
    bundle, skill = bundle_skill
    target = cache_root / "some-marketplace" / bundle / version / "skills" / skill
    target.mkdir(parents=True, exist_ok=True)
    script = target / pathlib.Path(rel_path)
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(content)
    return script


def test_resolves_script_from_the_only_cached_version(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    expected = _make_cached_skill(tmp_path, ("b", "s"), "0.1.0", "run.py")
    assert mod.resolve_skill_script("b", "s", "run.py") == expected


def test_prefers_the_newest_version_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    _make_cached_skill(tmp_path, ("b", "s"), "0.1.0", "run.py", content="old")
    newest = _make_cached_skill(tmp_path, ("b", "s"), "0.1.1", "run.py", content="new")
    result = mod.resolve_skill_script("b", "s", "run.py")
    assert result == newest
    assert result.read_text() == "new"


def test_skips_a_version_directory_marked_orphaned(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    orphaned = _make_cached_skill(tmp_path, ("b", "s"), "0.1.1", "run.py")
    (orphaned.parents[2] / ".orphaned_at").write_text("2026-08-01")
    live = _make_cached_skill(tmp_path, ("b", "s"), "0.1.0", "run.py")
    assert mod.resolve_skill_script("b", "s", "run.py") == live


def test_falls_back_to_a_repo_checkout_when_cache_has_nothing(tmp_path, monkeypatch):
    empty_cache = tmp_path / "cache"
    empty_cache.mkdir()
    repo = tmp_path / "repo"
    script = repo / "plugins" / "b" / "skills" / "s" / "run.py"
    script.parent.mkdir(parents=True)
    script.write_text("")
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [empty_cache])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [repo])
    assert mod.resolve_skill_script("b", "s", "run.py") == script


def test_returns_none_when_nothing_resolves(tmp_path, monkeypatch):
    empty_cache = tmp_path / "cache"
    empty_cache.mkdir()
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [empty_cache])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [tmp_path / "nowhere"])
    assert mod.resolve_skill_script("b", "s", "run.py") is None


def _run(*args, env=None):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        input="{}",
        capture_output=True,
        text=True,
        env=env,
    )


def test_help_exits_zero_without_requiring_source():
    result = _run("--help")
    assert result.returncode == 0
    assert "Usage:" in result.stdout


def test_missing_source_is_a_usage_error():
    result = _run()
    assert result.returncode != 0


def test_unresolvable_targets_fail_open_instead_of_blocking_the_tool_call(
    tmp_path, monkeypatch
):
    # Points both cache and repo fallback at empty dirs so resolution
    # genuinely fails, then asserts the hook still allows the tool call
    # through -- this is the exact failure mode that took the session down.
    empty_cache = tmp_path / "cache"
    empty_cache.mkdir()
    env = {
        **__import__("os").environ,
        "HOOK_DISPATCH_CACHE_ROOT": str(empty_cache),
        "MANIFEST_REPO_DIR": str(tmp_path / "nowhere"),
    }
    result = _run("--source", "claude", env=env)
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert payload["continue"] is True


def test_resolved_targets_are_dispatched_with_stdin_forwarded(tmp_path):
    unified_dir = tmp_path / "cache" / "mp" / "manifest-workspace" / "0.1.0" / "skills" / "ai-hooks-integration" / "scripts" / "runtime"
    unified_dir.mkdir(parents=True)
    unified = unified_dir / "unified_hook.py"
    unified.write_text(
        "import sys\n"
        "print(sys.stdin.read().strip())\n"
    )

    handler_dir = tmp_path / "cache" / "mp" / "manifest-forge" / "0.1.0" / "skills" / "pr-monitor" / "scripts"
    handler_dir.mkdir(parents=True)
    (handler_dir / "pr_create_trigger.py").write_text("")

    env = {**__import__("os").environ, "HOOK_DISPATCH_CACHE_ROOT": str(tmp_path / "cache")}
    result = _run("--source", "claude", env=env)
    assert result.returncode == 0
    assert result.stdout.strip() == "{}"
