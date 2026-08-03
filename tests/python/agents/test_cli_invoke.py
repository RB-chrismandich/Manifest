"""Tests for agents.cli_invoke shared headless CLI seam."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[3] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

from agents.cli_invoke import (
    CliRoute,
    build_subprocess_argv,
    resolve_cli_route,
    resolve_provider_model,
    resolve_role_model_tier,
)
from agents.config import Config


def _config(tmp_path: Path) -> Config:
    return Config(config_path=str(tmp_path / "missing.yml"))


def test_resolve_provider_model_translates_claude_tier_alias(tmp_path):
    # Regression: synthesis passes its claude tier ("sonnet") to whichever
    # provider CLI answers the route; antigravity's tiers are mini/flash/
    # advanced, so the raw alias leaked as `--model sonnet` and agy rejected
    # it. Aliases must translate through the documented tier equivalence
    # (mini/haiku, flash/sonnet, advanced/opus/pro).
    cfg = _config(tmp_path)
    resolved = resolve_provider_model(cfg, "antigravity", "sonnet")
    assert resolved == cfg.get("model_tiers.antigravity.flash")
    assert resolve_provider_model(cfg, "antigravity", "haiku") == cfg.get(
        "model_tiers.antigravity.mini"
    )
    assert resolve_provider_model(cfg, "codex", "opus") == cfg.get(
        "model_tiers.codex.advanced"
    )


def test_resolve_provider_model_keeps_custom_passthrough(tmp_path):
    # Custom/full model names that are not tier aliases still pass through
    # verbatim (devin relies on this), and "auto" still means no --model.
    cfg = _config(tmp_path)
    assert (
        resolve_provider_model(cfg, "codex", "gpt-5.6-sol-high") == "gpt-5.6-sol-high"
    )
    assert resolve_provider_model(cfg, "codex", "auto") is None


def test_resolve_role_model_tier_from_frontmatter(tmp_path):
    charter = tmp_path / "qa-critic.md"
    charter.write_text("---\nname: qa\nmodel: flash\n---\nbody\n", encoding="utf-8")
    assert resolve_role_model_tier(charter) == "flash"


def test_resolve_role_model_tier_defaults_sonnet(tmp_path):
    charter = tmp_path / "bare.md"
    charter.write_text("# no frontmatter\n", encoding="utf-8")
    assert resolve_role_model_tier(charter) == "sonnet"


def test_resolve_cli_route_env_cli_override(tmp_path, monkeypatch):
    monkeypatch.setenv("CDDL_INVOKE_CLI", "agy")
    monkeypatch.setattr(
        "agents.cli_invoke.cli_provider_available",
        lambda config, provider, binary_override=None: provider == "antigravity",
    )
    route = resolve_cli_route(
        _config(tmp_path),
        section="cddl_invoke",
        env_prefix="CDDL_INVOKE",
        allow_sdk=False,
    )
    assert route == CliRoute("cli", "antigravity", binary_override="agy")


def test_resolve_cli_route_skillclaw_section(tmp_path, monkeypatch):
    monkeypatch.delenv("EVOLVE_CLI", raising=False)
    monkeypatch.delenv("EVOLVE_PROVIDER", raising=False)

    def avail(config, provider, binary_override=None):
        return provider == "gemini"

    monkeypatch.setattr("agents.cli_invoke.cli_provider_available", avail)
    route = resolve_cli_route(
        _config(tmp_path),
        section="skillclaw_evolve",
        env_prefix="EVOLVE",
        allow_sdk=False,
    )
    assert route == CliRoute("cli", "gemini")


def test_build_subprocess_argv_claude_uses_stdin(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "agents.cli_invoke.cli_provider_available",
        lambda *a, **k: True,
    )
    config = _config(tmp_path)
    route = CliRoute("cli", "claude")
    argv, stdin = build_subprocess_argv(config, route, "hello prompt")
    assert argv == ["claude", "-p"]
    assert stdin == "hello prompt"


def test_resolve_cli_route_sdk_only_when_allowed(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(
        "agents.cli_invoke.cli_provider_available", lambda *a, **k: False
    )
    from agents import cli_invoke as mod

    original = mod.HAS_ANTHROPIC
    mod.HAS_ANTHROPIC = True
    try:
        denied = resolve_cli_route(
            _config(tmp_path),
            section="cddl_invoke",
            env_prefix="CDDL_INVOKE",
            allow_sdk=False,
        )
        allowed = resolve_cli_route(
            _config(tmp_path),
            section="synthesis",
            env_prefix="SYNTH",
            allow_sdk=True,
        )
        assert denied is None
        assert allowed == CliRoute("sdk", "claude")
    finally:
        mod.HAS_ANTHROPIC = original
