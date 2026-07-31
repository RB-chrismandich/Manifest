"""Fallback-chain resolution in budget_broker.

Written BEFORE the CON-003 refactor that removes the module's hand-copied model
table, to pin the behavior that must survive it. The values below are asserted
against `parallel_agent.yml` rather than written out again — a test that
restates the constant is a fourth copy of the thing the refactor is deleting.
"""

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "configs" / "claude" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import budget_broker

REPO_YAML = REPO_ROOT / "configs" / "claude" / "config" / "parallel_agent.yml"


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load(REPO_YAML.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _use_repo_config(monkeypatch, tmp_path):
    """Point Config at the repo YAML.

    Without this the module under test resolves `~/.claude/config`, so the test
    would pass or fail on whatever the developer last deployed — the ambient
    state would be the fixture.
    """
    monkeypatch.setenv("MANIFEST_CONFIG_DIR", str(REPO_YAML.parent))


def chain_for(config, provider):
    """The chain the YAML says a provider should fall through."""
    tiers = config["credit_fallback"][provider]
    tier_map = config["model_tiers"][provider]
    return [tier_map[t] for t in tiers if t in tier_map]


BINARIES = [
    ("claude", "claude"),
    ("gemini", "gemini"),
    ("cursor-agent", "cursor"),
    ("codex", "codex"),
    ("agy", "antigravity"),
]


@pytest.mark.parametrize("binary,provider", BINARIES, ids=[b for b, _ in BINARIES])
def test_first_tier_falls_through_to_the_second(config, binary, provider):
    expected = chain_for(config, provider)
    if len(expected) < 2:
        pytest.skip(f"{provider} has no second tier to fall to")
    assert budget_broker.get_fallback_model(binary, expected[0]) == expected[1]


@pytest.mark.parametrize("binary,provider", BINARIES, ids=[b for b, _ in BINARIES])
def test_last_tier_has_nowhere_left_to_fall(config, binary, provider):
    expected = chain_for(config, provider)
    assert budget_broker.get_fallback_model(binary, expected[-1]) is None


@pytest.mark.parametrize("binary,provider", BINARIES, ids=[b for b, _ in BINARIES])
def test_unknown_model_falls_to_the_cheapest(config, binary, provider):
    """An unrecognized model is treated as "start at the bottom", not an error."""
    expected = chain_for(config, provider)
    assert budget_broker.get_fallback_model(binary, "no-such-model") == expected[-1]


def test_unknown_binary_yields_none():
    assert budget_broker.get_fallback_model("not-a-cli", "anything") is None


def test_chains_agree_with_parallel_agent_yml(config):
    """The regression this refactor exists to prevent: a hand-copied chain
    silently drifting from the registry every other consumer reads."""
    for binary, provider in BINARIES:
        expected = chain_for(config, provider)
        walked = [expected[0]]
        while True:
            nxt = budget_broker.get_fallback_model(binary, walked[-1])
            if nxt is None:
                break
            walked.append(nxt)
        assert walked == expected, f"{binary} chain drifted from parallel_agent.yml"
