"""O2 fix: setup --enable-review-gate must never overwrite an existing but
unreadable/invalid delegation.json with factory defaults, and a successful
write must be atomic with a .bak backup of the prior valid config.
"""

import json

from _delegate_harness import _run


def test_setup_gate_refuses_to_overwrite_invalid_existing_config(env_factory):
    env = env_factory()
    config_path = None
    for key in ("MANIFEST_CONFIG_DIR",):
        config_path = env[key]
    delegation_json = __import__("pathlib").Path(config_path) / "delegation.json"
    delegation_json.write_text("{ not json")
    before = delegation_json.read_bytes()

    result = _run(env, "setup", "--enable-review-gate")

    assert result.returncode == 2, result.stderr
    assert "refusing to overwrite" in result.stderr
    after = delegation_json.read_bytes()
    assert after == before, "invalid config must be left byte-identical"
    assert not delegation_json.with_suffix(".json.bak").exists()


def test_setup_gate_valid_config_writes_atomically_with_backup(env_factory):
    from pathlib import Path

    env = env_factory()
    config_dir = Path(env["MANIFEST_CONFIG_DIR"])
    delegation_json = config_dir / "delegation.json"
    prior = {"default_backend": "stub", "review_gate": {"enabled": False}}
    delegation_json.write_text(json.dumps(prior))

    result = _run(env, "setup", "--enable-review-gate", "--json")

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["review_gate"]["enabled"] is True

    data = json.loads(delegation_json.read_text())
    assert data["default_backend"] == "stub"  # preserved, not clobbered
    assert data["review_gate"]["enabled"] is True

    backup = config_dir / "delegation.json.bak"
    assert backup.exists()
    assert json.loads(backup.read_text()) == prior


def test_setup_gate_creates_config_when_absent(env_factory):
    from pathlib import Path

    env = env_factory()
    delegation_json = Path(env["MANIFEST_CONFIG_DIR"]) / "delegation.json"
    delegation_json.unlink()

    result = _run(env, "setup", "--enable-review-gate")

    assert result.returncode == 0, result.stderr
    assert delegation_json.exists()
    data = json.loads(delegation_json.read_text())
    assert data["review_gate"]["enabled"] is True
