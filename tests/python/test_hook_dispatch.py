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
import os
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


def _isolated_env(tmp_path, **overrides):
    """Base env pointing every resolution source at nothing on this machine.

    Without this, tests run against the real ~/.claude/plugins/installed_plugins.json
    -- on a machine with ai-hooks-integration actually installed (like the one
    that wrote this fix), resolution "succeeds" via the real install and the
    real hook's own fail-open response is indistinguishable from the
    dispatcher's, so a test meant to exercise "resolution failed" silently
    exercises "resolution succeeded" instead and still passes.
    """
    empty_cache = tmp_path / "empty-cache"
    empty_cache.mkdir(exist_ok=True)
    env = {
        **os.environ,
        "HOOK_DISPATCH_CACHE_ROOT": str(empty_cache),
        "HOOK_DISPATCH_INSTALLED_PLUGINS": str(tmp_path / "no-installed-plugins.json"),
        "MANIFEST_REPO_DIR": str(tmp_path / "no-repo-checkout"),
    }
    env.update(overrides)
    return env


def _make_cached_skill(cache_root, bundle_skill, version, rel_path, content=""):
    bundle, skill = bundle_skill
    # The marketplace resolution is scoped to. Was "some-marketplace", which
    # quietly asserted that ANY marketplace could supply the script.
    target = cache_root / "manifest" / bundle / version / "skills" / skill
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


def test_unresolvable_targets_fail_open_instead_of_blocking_the_tool_call(tmp_path):
    # Isolates every resolution source so resolution genuinely fails, then
    # asserts the hook still allows the tool call through -- this is the
    # exact failure mode that took the session down.
    result = _run("--source", "claude", env=_isolated_env(tmp_path))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert payload["continue"] is True


def test_resolved_targets_are_dispatched_with_stdin_forwarded(tmp_path):
    cache = tmp_path / "cache"
    # "manifest", not an arbitrary marketplace name: resolution is scoped to the
    # marketplace it was asked for, so a fixture elsewhere would never be found.
    unified_dir = (
        cache
        / "manifest"
        / "manifest-workspace"
        / "0.1.0"
        / "skills"
        / "ai-hooks-integration"
        / "scripts"
        / "runtime"
    )
    unified_dir.mkdir(parents=True)
    unified = unified_dir / "unified_hook.py"
    unified.write_text("import sys\nprint(sys.stdin.read().strip())\n")

    handler_dir = (
        cache
        / "manifest"
        / "manifest-forge"
        / "0.1.0"
        / "skills"
        / "pr-monitor"
        / "scripts"
    )
    handler_dir.mkdir(parents=True)
    (handler_dir / "pr_create_trigger.py").write_text("")

    env = _isolated_env(tmp_path, HOOK_DISPATCH_CACHE_ROOT=str(cache))
    result = _run("--source", "claude", env=env)
    assert result.returncode == 0
    assert result.stdout.strip() == "{}"


def test_prefers_double_digit_version_over_single_digit(tmp_path, monkeypatch):
    # The regression a plain string sort gets wrong: "0.1.9" > "0.1.10"
    # lexicographically even though 10 > 9 numerically.
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    _make_cached_skill(tmp_path, ("b", "s"), "0.1.9", "run.py", content="old")
    newest = _make_cached_skill(tmp_path, ("b", "s"), "0.1.10", "run.py", content="new")
    result = mod.resolve_skill_script("b", "s", "run.py")
    assert result == newest
    assert result.read_text() == "new"


def test_a_directory_name_that_is_not_a_dotted_version_never_shadows_a_real_one(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    _make_cached_skill(tmp_path, ("b", "s"), "not-a-version", "run.py", content="junk")
    real = _make_cached_skill(tmp_path, ("b", "s"), "0.1.0", "run.py", content="real")
    result = mod.resolve_skill_script("b", "s", "run.py")
    assert result == real
    assert result.read_text() == "real"


def test_resolves_via_installed_plugins_json_before_scanning_the_cache(
    tmp_path, monkeypatch
):
    # A same-named bundle in some other marketplace must not be able to
    # supply the script: the installed_plugins.json record is scoped to
    # bundle@marketplace, not bundle alone.
    other_marketplace_version = _make_cached_skill(
        tmp_path, ("b", "s"), "9.9.9", "run.py", content="wrong marketplace"
    )
    install_dir = tmp_path / "installed" / "b"
    (install_dir / "skills" / "s").mkdir(parents=True)
    correct = install_dir / "skills" / "s" / "run.py"
    correct.write_text("correct install")

    installed_plugins = tmp_path / "installed_plugins.json"
    installed_plugins.write_text(
        json.dumps({"plugins": {"b@manifest": [{"installPath": str(install_dir)}]}})
    )

    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    monkeypatch.setattr(mod, "INSTALLED_PLUGINS_PATH", installed_plugins)

    result = mod.resolve_skill_script("b", "s", "run.py")
    assert result == correct
    assert result != other_marketplace_version
    assert result.read_text() == "correct install"


def test_unreadable_cache_directory_fails_open_rather_than_raising(
    tmp_path, monkeypatch, capsys
):
    # monkeypatch only affects this process, so this exercises main()
    # in-process rather than through _run's subprocess.
    class RaisingPath:
        """Stands in for a cache path that vanishes mid-scan.

        Resolution now indexes `cache_root / marketplace / bundle` before
        listing versions, so the stub has to survive `/` and still blow up on
        the listing -- otherwise it would raise TypeError and "pass" for a
        reason that has nothing to do with the fail-open guarantee.
        """

        def __truediv__(self, _other):
            return self

        def is_dir(self):
            return True

        def iterdir(self):
            raise PermissionError("gone mid-scan")

    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [RaisingPath()])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    monkeypatch.setattr(
        mod, "INSTALLED_PLUGINS_PATH", tmp_path / "no-installed-plugins.json"
    )
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("{}"))

    rc = mod.main(["--source", "claude"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"


# --------------------------------------------------------------------------- #
# Marketplace scoping of the cache fallback
#
# `_installed_plugin_dir` is scoped to bundle@marketplace, and its docstring
# already warned that scanning the cache by bundle name alone "can't tell
# Manifest's manifest-workspace apart from a same-named bundle in some other
# configured marketplace". The fallback did exactly that: it iterated every
# marketplace directory and picked the highest version number found. Whatever it
# picked was then EXECUTED on every matching tool event.
#
# This machine has ten marketplaces cached, including transient temp_git_* dirs,
# so the collision is not hypothetical.
# --------------------------------------------------------------------------- #


def _cache_skill_in(cache_root, marketplace, bundle, skill, version, rel_path, content):
    target = cache_root / marketplace / bundle / version / "skills" / skill
    target.mkdir(parents=True, exist_ok=True)
    script = target / rel_path
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(content)
    return script


def test_a_foreign_marketplace_cannot_supply_the_script(tmp_path, monkeypatch):
    """The core substitution: no Manifest install, a same-named bundle cached
    elsewhere. Resolution must decline rather than execute the stranger."""
    foreign = _cache_skill_in(
        tmp_path, "someone-elses-marketplace", "b", "s", "9.9.9", "run.py", "foreign"
    )
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    monkeypatch.setattr(mod, "INSTALLED_PLUGINS_PATH", tmp_path / "absent.json")

    result = mod.resolve_skill_script("b", "s", "run.py", marketplace="manifest")
    assert result is None, f"resolved a foreign marketplace's script: {result}"
    assert result != foreign


def test_foreign_marketplace_targets_are_not_dispatched(tmp_path):
    """Resolution failure must reach main's allow response, not execution."""
    cache = tmp_path / "cache"
    marketplace = "someone-elses-marketplace"
    _cache_skill_in(
        cache,
        marketplace,
        "manifest-workspace",
        "ai-hooks-integration",
        "9.9.9",
        "scripts/runtime/unified_hook.py",
        "print('FOREIGN_DISPATCH')\n",
    )
    _cache_skill_in(
        cache,
        marketplace,
        "manifest-forge",
        "pr-monitor",
        "9.9.9",
        "scripts/pr_create_trigger.py",
        "",
    )

    env = _isolated_env(tmp_path, HOOK_DISPATCH_CACHE_ROOT=str(cache))
    result = _run("--source", "claude", env=env)

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["hookSpecificOutput"]["permissionDecision"] == "allow"
    assert "FOREIGN_DISPATCH" not in result.stdout


def test_a_higher_foreign_version_does_not_outrank_the_right_marketplace(
    tmp_path, monkeypatch
):
    """Version ordering must not reach across the trust boundary: 9.9.9 in the
    wrong marketplace loses to 0.0.1 in the right one."""
    _cache_skill_in(
        tmp_path, "someone-elses-marketplace", "b", "s", "9.9.9", "run.py", "foreign"
    )
    ours = _cache_skill_in(tmp_path, "manifest", "b", "s", "0.0.1", "run.py", "ours")
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    monkeypatch.setattr(mod, "INSTALLED_PLUGINS_PATH", tmp_path / "absent.json")

    assert mod.resolve_skill_script("b", "s", "run.py", marketplace="manifest") == ours


def test_a_stale_install_record_still_cannot_fall_through_to_a_stranger(
    tmp_path, monkeypatch
):
    """The exact gap: installed_plugins.json present but its path is gone, so
    resolution proceeds to the cache fallback."""
    foreign = _cache_skill_in(
        tmp_path, "someone-elses-marketplace", "b", "s", "9.9.9", "run.py", "foreign"
    )
    stale = tmp_path / "installed_plugins.json"
    stale.write_text(
        json.dumps(
            {"plugins": {"b@manifest": [{"installPath": str(tmp_path / "gone")}]}}
        )
    )
    monkeypatch.setattr(mod, "PLUGIN_CACHE_ROOTS", [tmp_path])
    monkeypatch.setattr(mod, "REPO_FALLBACKS", [])
    monkeypatch.setattr(mod, "INSTALLED_PLUGINS_PATH", stale)

    result = mod.resolve_skill_script("b", "s", "run.py", marketplace="manifest")
    assert result is None and result != foreign
