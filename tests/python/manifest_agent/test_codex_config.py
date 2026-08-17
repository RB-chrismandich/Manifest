import threading
from pathlib import Path

import pytest

from manifest_agent.codex_config import (
    CodexConfigError,
    content_sha256,
    observe_plugin_enabled_rollback,
    plugin_enabled_change_from_metadata,
    rollback_plugin_enabled,
    set_plugin_enabled,
)


def test_content_hash_cas_and_field_only_rollback(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        'theme = "light"\n[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n'
    )
    before = content_sha256(path.read_bytes())
    change = set_plugin_enabled(
        path, "i-have-adhd@i-have-adhd", False, expected_sha256=before
    )
    path.write_text(path.read_text() + 'later = "user"\n')
    rollback_plugin_enabled(path, change)
    assert "enabled = true" in path.read_text()
    assert 'later = "user"' in path.read_text()


def test_cas_rejects_stale_hash(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("")
    with pytest.raises(CodexConfigError, match="precondition"):
        set_plugin_enabled(
            path, "i-have-adhd@i-have-adhd", False, expected_sha256="0" * 64
        )


def test_rollback_blocks_later_owned_field_change(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n')
    change = set_plugin_enabled(path, "i-have-adhd@i-have-adhd", False)
    path.write_text(path.read_text().replace("false", "true"))
    with pytest.raises(CodexConfigError, match="field changed"):
        rollback_plugin_enabled(path, change)


def test_rollback_restores_absent_enabled_key_exactly(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(
        '[plugins."i-have-adhd@i-have-adhd"]\nchannel = "stable"\n',
        encoding="utf-8",
    )

    change = set_plugin_enabled(path, "i-have-adhd@i-have-adhd", False)
    assert change.previous is None
    rollback_plugin_enabled(path, change)

    text = path.read_text(encoding="utf-8")
    assert "enabled" not in text
    assert 'channel = "stable"' in text


def test_rollback_removes_plugin_table_created_by_mutation(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    before = b'theme = "light"\n'
    path.write_bytes(before)

    change = set_plugin_enabled(path, "i-have-adhd@i-have-adhd", False)
    rollback_plugin_enabled(path, change)

    assert path.read_bytes() == before
    assert observe_plugin_enabled_rollback(path, change) == "completed"


def test_created_plugin_table_change_blocks_rollback(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('theme = "light"\n', encoding="utf-8")
    change = set_plugin_enabled(path, "i-have-adhd@i-have-adhd", False)
    path.write_text(path.read_text() + 'channel = "user"\n', encoding="utf-8")
    changed = path.read_bytes()

    with pytest.raises(CodexConfigError, match="created plugin table changed"):
        rollback_plugin_enabled(path, change)

    assert path.read_bytes() == changed


def test_created_plugin_table_residue_is_not_completed(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('theme = "light"\n', encoding="utf-8")
    change = set_plugin_enabled(path, "i-have-adhd@i-have-adhd", False)
    path.write_text(path.read_text().replace("enabled = false\n", ""), encoding="utf-8")

    assert observe_plugin_enabled_rollback(path, change) == "ambiguous"


def test_legacy_absent_enabled_metadata_requires_table_provenance() -> None:
    with pytest.raises(CodexConfigError, match="metadata is invalid"):
        plugin_enabled_change_from_metadata(
            "i-have-adhd@i-have-adhd",
            {"previous": None, "current": False, "written_sha256": "0" * 64},
        )


def test_cooperative_lock_serializes_concurrent_config_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import manifest_agent.codex_config as config_module

    path = tmp_path / "config.toml"
    path.write_text('[plugins."i-have-adhd@i-have-adhd"]\nenabled = true\n')
    entered = threading.Event()
    release = threading.Event()
    real_atomic = config_module._atomic_cas

    def blocked_atomic(target, before, candidate):
        if b"false" in candidate and not entered.is_set():
            entered.set()
            assert release.wait(5)
        real_atomic(target, before, candidate)

    monkeypatch.setattr(config_module, "_atomic_cas", blocked_atomic)
    errors = []

    def write(value):
        try:
            set_plugin_enabled(path, "i-have-adhd@i-have-adhd", value)
        except Exception as error:  # pragma: no cover - asserted via errors
            errors.append(error)

    first = threading.Thread(target=write, args=(False,))
    second = threading.Thread(target=write, args=(True,))
    first.start()
    assert entered.wait(5)
    second.start()
    release.set()
    first.join(5)
    second.join(5)

    assert errors == []
    assert "enabled = true" in path.read_text(encoding="utf-8")
