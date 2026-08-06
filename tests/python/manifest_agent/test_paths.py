"""XDG paths used by coordinator state and receipts."""

from manifest_agent.paths import xdg_paths


def test_xdg_paths_never_fall_back_to_claude_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    paths = xdg_paths()

    assert paths.state == tmp_path / ".local/state/manifest"
    assert ".claude" not in str(paths)


def test_xdg_paths_respect_each_explicit_xdg_home(monkeypatch, tmp_path):
    homes = {
        "XDG_CONFIG_HOME": tmp_path / "config-home",
        "XDG_DATA_HOME": tmp_path / "data-home",
        "XDG_STATE_HOME": tmp_path / "state-home",
        "XDG_CACHE_HOME": tmp_path / "cache-home",
    }
    for name, path in homes.items():
        monkeypatch.setenv(name, str(path))

    paths = xdg_paths()

    assert paths.config == homes["XDG_CONFIG_HOME"] / "manifest"
    assert paths.data == homes["XDG_DATA_HOME"] / "manifest"
    assert paths.state == homes["XDG_STATE_HOME"] / "manifest"
    assert paths.cache == homes["XDG_CACHE_HOME"] / "manifest"
