"""Tests for cddl_invoke.py headless CDDL persona seam."""

from __future__ import annotations

import io
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "configs/claude/scripts"
sys.path.insert(0, str(SCRIPTS))

import cddl_invoke
from manifest_model_policy import CliRoute


def test_main_invokes_charter_and_body(tmp_path, monkeypatch):
    charter = tmp_path / "critic.md"
    charter.write_text("---\nmodel: sonnet\n---\n# Charter\n", encoding="utf-8")
    seen: dict[str, str] = {}

    def fake_invoke(route, prompt, config, **kwargs):
        seen["prompt"] = prompt
        seen["tier"] = kwargs.get("model_tier")
        return "verdict: pass\n"

    monkeypatch.setattr(sys, "stdin", io.StringIO("dispatch body\n"))
    monkeypatch.setattr("cddl_invoke.load_default_policy", lambda: {})
    monkeypatch.setattr(
        "cddl_invoke.resolve_cli_route",
        lambda *a, **k: CliRoute("cli", "antigravity"),
    )
    monkeypatch.setattr("cddl_invoke.run_headless_prompt", fake_invoke)

    rc = cddl_invoke.main(
        ["--charter", str(charter), "--timeout", "30"],
    )
    assert rc == 0
    assert "# Charter" in seen["prompt"]
    assert "dispatch body" in seen["prompt"]
    assert seen["tier"] == "sonnet"


def test_main_no_cli_returns_6(monkeypatch):
    monkeypatch.setattr("cddl_invoke.load_default_policy", lambda: {})
    monkeypatch.setattr("cddl_invoke.resolve_cli_route", lambda *a, **k: None)
    rc = cddl_invoke.main(["--charter", "/tmp/x.md"])
    assert rc == 6
