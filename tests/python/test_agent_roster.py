from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
ROSTER = REPO / "configs/claude/config/agent_roster.yml"
PARALLEL_AGENT = REPO / "configs/claude/config/parallel_agent.yml"

EXPECTED_AGENTS = {"claude", "gemini", "cursor", "codex", "antigravity"}
REQUIRED_KEYS = {
    "name",
    "binary",
    "home_dir",
    "prompt_args",
    "model_args",
    "auth_check",
    "enabled_default",
}


def load_roster():
    return yaml.safe_load(ROSTER.read_text())


def load_parallel_agent():
    return yaml.safe_load(PARALLEL_AGENT.read_text())


def test_roster_exists_and_parses():
    data = load_roster()
    assert isinstance(data, dict)
    assert "agents" in data


def test_all_five_agents_present():
    assert set(load_roster()["agents"]) == EXPECTED_AGENTS


def test_every_entry_has_all_six_keys():
    for name, entry in load_roster()["agents"].items():
        assert set(entry) == REQUIRED_KEYS, name


def test_home_dir_starts_with_tilde_dot():
    for name, entry in load_roster()["agents"].items():
        assert entry["home_dir"].startswith("~/."), name


def test_name_field_matches_agent_key():
    for name, entry in load_roster()["agents"].items():
        assert entry["name"] == name, name


def test_enabled_default_is_bool():
    for name, entry in load_roster()["agents"].items():
        assert isinstance(entry["enabled_default"], bool), name


def test_prompt_args_and_model_args_are_lists():
    for name, entry in load_roster()["agents"].items():
        assert isinstance(entry["prompt_args"], list), name
        assert isinstance(entry["model_args"], list), name


# Drift guard: parallel_agent.yml's cli_agents[agent].binary must match
# agent_roster.yml's agents[agent].binary for all 5 agents. parallel_agent.yml
# keeps its own tuning tables (model_tiers, rate limits, credit_fallback) —
# this is not a migration, just a guard that the two files agree on the fact
# they share.
def test_binary_matches_parallel_agent_cli_agents():
    roster = load_roster()["agents"]
    cli_agents = load_parallel_agent()["cli_agents"]
    for name in EXPECTED_AGENTS:
        assert roster[name]["binary"] == cli_agents[name]["binary"], name
