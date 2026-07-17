from pathlib import Path
import yaml

REPO = Path(__file__).resolve().parents[2]
REG = REPO / "configs/claude/config/tracker_providers.yml"

def load():
    return yaml.safe_load(REG.read_text())

def test_registry_exists_and_parses():
    data = load()
    assert isinstance(data, dict)

def test_all_four_providers_present():
    assert set(load()["providers"]) == {"github", "gitlab", "linear", "jira"}

def test_access_is_ordered_list_from_allowed_methods():
    allowed = {"mcp", "cli", "git", "api"}
    for name, p in load()["providers"].items():
        assert isinstance(p["access"], list) and p["access"], name
        assert set(p["access"]) <= allowed, name

def test_jira_is_mcp_only_and_has_tool_map():
    jira = load()["providers"]["jira"]
    assert jira["access"] == ["mcp"]
    assert "transition" in jira["mcp_tools"]

def test_status_maps_cover_all_canonical_statuses():
    canon = {"planned", "in-progress", "needs-review", "done"}
    for name, p in load()["providers"].items():
        assert set(p["status_map"]) == canon, name

def test_every_provider_declares_verified_flag():
    for name, p in load()["providers"].items():
        assert isinstance(p["verified"], bool), name

def test_default_provider_is_a_known_provider():
    data = load()
    assert data["default_provider"] in data["providers"]
