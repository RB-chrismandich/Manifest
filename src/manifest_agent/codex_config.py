"""Content-hash CAS editing for one owned Codex plugin enabled field."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import tempfile
import tomllib
from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CodexConfigError(RuntimeError):
    """The requested narrow mutation cannot be proven safe."""


_MANIFEST_PLUGIN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*@manifest$")


@dataclass(frozen=True)
class PluginEnabledChange:
    plugin_id: str
    previous: bool | None
    current: bool
    before_sha256: str
    written_sha256: str
    table_existed: bool = True
    separator_added: bool = False


@contextmanager
def _config_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = path.with_name(f".{path.name}.manifest.lock")
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def content_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(path: Path) -> tuple[bytes, dict]:
    if path.is_symlink():
        raise CodexConfigError("Codex config path must not be a symlink")
    try:
        data = path.read_bytes() if path.exists() else b""
        document = tomllib.loads(data.decode("utf-8")) if data else {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        raise CodexConfigError("Codex config is unreadable or malformed") from error
    return data, document


def _table_pattern(plugin_id: str) -> re.Pattern[str]:
    escaped = re.escape(plugin_id)
    return re.compile(
        rf'(?ms)^\[plugins\.(?:"{escaped}"|\'{escaped}\')\]\s*\n(?P<body>.*?)(?=^\[|\Z)'
    )


def _candidate(data: bytes, plugin_id: str, enabled: bool) -> tuple[bytes, bool | None]:
    text = data.decode("utf-8")
    table_pattern = _table_pattern(plugin_id)
    matches = list(table_pattern.finditer(text))
    if len(matches) > 1:
        raise CodexConfigError("Codex config contains duplicate matching plugin tables")
    rendered = "true" if enabled else "false"
    previous: bool | None = None
    if matches:
        match = matches[0]
        body = match.group("body")
        keys = list(re.finditer(r"(?m)^enabled\s*=\s*(true|false)\s*(?:#.*)?$", body))
        if len(keys) > 1:
            raise CodexConfigError("Codex plugin table contains duplicate enabled keys")
        if keys:
            key = keys[0]
            previous = key.group(1) == "true"
            new_body = body[: key.start(1)] + rendered + body[key.end(1) :]
        else:
            new_body = f"enabled = {rendered}\n" + body
        candidate = text[: match.start("body")] + new_body + text[match.end("body") :]
    else:
        separator = "" if not text or text.endswith("\n\n") else "\n"
        candidate = (
            text + separator + f'[plugins."{plugin_id}"]\n' + f"enabled = {rendered}\n"
        )
    return candidate.encode("utf-8"), previous


def _atomic_cas(path: Path, before: bytes, candidate: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    current = path.read_bytes() if path.exists() else b""
    if content_sha256(current) != content_sha256(before):
        raise CodexConfigError("Codex config changed during compare-and-swap")
    descriptor = -1
    temporary: Path | None = None
    try:
        descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary = Path(name)
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(candidate)
            stream.flush()
            os.fsync(stream.fileno())
        if content_sha256(
            path.read_bytes() if path.exists() else b""
        ) != content_sha256(before):
            raise CodexConfigError("Codex config changed during compare-and-swap")
        os.replace(temporary, path)
        temporary = None
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except OSError as error:
        raise CodexConfigError("unable to update Codex config atomically") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare_plugin_enabled(
    path: Path,
    plugin_id: str,
    enabled: bool,
    *,
    expected_sha256: str | None = None,
) -> PluginEnabledChange:
    """Prepare a content-bound field change without mutating the config."""
    if plugin_id != "i-have-adhd@i-have-adhd":
        raise CodexConfigError("only the exact upstream ADHD plugin may be edited")
    return _prepare_plugin_enabled(
        path, plugin_id, enabled, expected_sha256=expected_sha256
    )


def prepare_manifest_plugin_enabled(
    path: Path,
    plugin_id: str,
    enabled: bool,
    *,
    expected_sha256: str | None = None,
) -> PluginEnabledChange:
    """Prepare restoration of one validated Manifest native registration."""
    if _MANIFEST_PLUGIN_ID.fullmatch(plugin_id) is None:
        raise CodexConfigError("only a valid Manifest plugin may be restored")
    return _prepare_plugin_enabled(
        path, plugin_id, enabled, expected_sha256=expected_sha256
    )


def _prepare_plugin_enabled(
    path: Path,
    plugin_id: str,
    enabled: bool,
    *,
    expected_sha256: str | None,
) -> PluginEnabledChange:
    before, original = _load(path)
    before_hash = content_sha256(before)
    if expected_sha256 is not None and expected_sha256 != before_hash:
        raise CodexConfigError("Codex config compare-and-swap precondition failed")
    candidate, previous = _candidate(before, plugin_id, enabled)
    try:
        parsed = tomllib.loads(candidate.decode("utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise CodexConfigError("Codex config candidate is invalid") from error
    expected = dict(original)
    plugins = dict(expected.get("plugins", {}))
    plugin = dict(plugins.get(plugin_id, {}))
    plugin["enabled"] = enabled
    plugins[plugin_id] = plugin
    expected["plugins"] = plugins
    if parsed != expected:
        raise CodexConfigError("Codex config mutation changed unrelated values")
    original_plugins = original.get("plugins", {})
    table_existed = isinstance(original_plugins, dict) and plugin_id in original_plugins
    separator_added = (
        not table_existed and bool(before) and not before.endswith(b"\n\n")
    )
    return PluginEnabledChange(
        plugin_id,
        previous,
        enabled,
        before_hash,
        content_sha256(candidate),
        table_existed,
        separator_added,
    )


def plugin_enabled_change_from_metadata(
    plugin_id: str, metadata: Mapping[str, Any]
) -> PluginEnabledChange:
    """Decode durable rollback metadata, accepting only unambiguous legacy rows."""
    previous = metadata.get("previous")
    table_existed = metadata.get("table_existed")
    separator_added = metadata.get("separator_added")
    if table_existed is None and separator_added is None and isinstance(previous, bool):
        table_existed = True
        separator_added = False
    if (
        (previous is not None and not isinstance(previous, bool))
        or not isinstance(metadata.get("current"), bool)
        or not isinstance(metadata.get("written_sha256"), str)
        or not isinstance(table_existed, bool)
        or not isinstance(separator_added, bool)
        or (not table_existed and previous is not None)
        or (table_existed and separator_added)
    ):
        raise CodexConfigError("plugin enabled rollback metadata is invalid")
    return PluginEnabledChange(
        plugin_id,
        previous,
        metadata["current"],
        "",
        metadata["written_sha256"],
        table_existed,
        separator_added,
    )


def apply_plugin_enabled(path: Path, change: PluginEnabledChange) -> None:
    """Apply one prepared change under the cooperative config lock."""
    with _config_lock(path):
        before, _ = _load(path)
        if content_sha256(before) != change.before_sha256:
            raise CodexConfigError("Codex config compare-and-swap precondition failed")
        candidate, previous = _candidate(before, change.plugin_id, change.current)
        if (
            previous is not change.previous
            or content_sha256(candidate) != change.written_sha256
        ):
            raise CodexConfigError("Codex config prepared mutation no longer matches")
        if candidate != before:
            _atomic_cas(path, before, candidate)


def set_plugin_enabled(
    path: Path,
    plugin_id: str,
    enabled: bool,
    *,
    expected_sha256: str | None = None,
) -> PluginEnabledChange:
    """Set one enabled field under a cooperative lock and content CAS."""
    with _config_lock(path):
        change = prepare_plugin_enabled(
            path, plugin_id, enabled, expected_sha256=expected_sha256
        )
        before, _ = _load(path)
        candidate, _ = _candidate(before, plugin_id, enabled)
        if candidate != before:
            _atomic_cas(path, before, candidate)
        return change


def set_manifest_plugin_enabled(
    path: Path,
    plugin_id: str,
    enabled: bool,
    *,
    expected_sha256: str | None = None,
) -> PluginEnabledChange:
    """Restore one Manifest registration under the same narrow CAS boundary."""
    with _config_lock(path):
        change = prepare_manifest_plugin_enabled(
            path, plugin_id, enabled, expected_sha256=expected_sha256
        )
        before, _ = _load(path)
        candidate, _ = _candidate(before, plugin_id, enabled)
        if candidate != before:
            _atomic_cas(path, before, candidate)
        return change


def rollback_plugin_enabled(path: Path, change: PluginEnabledChange) -> None:
    """Restore only the owned field while it still equals Manifest's value."""
    with _config_lock(path):
        current, document = _load(path)
        plugin = document.get("plugins", {}).get(change.plugin_id, {})
        if plugin.get("enabled") is not change.current:
            raise CodexConfigError("rollback blocked because the owned field changed")
        if change.previous is None:
            text = current.decode("utf-8")
            match = _table_pattern(change.plugin_id).search(text)
            if match is None:
                raise CodexConfigError(
                    "rollback blocked because the plugin table disappeared"
                )
            body = re.sub(
                r"(?m)^enabled\s*=\s*(?:true|false)\s*(?:#.*)?\n?",
                "",
                match.group("body"),
                count=1,
            )
            if change.table_existed:
                candidate_text = (
                    text[: match.start("body")] + body + text[match.end("body") :]
                )
            else:
                if body.strip():
                    raise CodexConfigError(
                        "rollback blocked because the created plugin table changed"
                    )
                start = match.start()
                if change.separator_added:
                    if start == 0 or text[start - 1] != "\n":
                        raise CodexConfigError(
                            "rollback blocked because plugin table provenance changed"
                        )
                    start -= 1
                candidate_text = text[:start] + text[match.end() :]
            try:
                if candidate_text:
                    tomllib.loads(candidate_text)
            except tomllib.TOMLDecodeError as error:
                raise CodexConfigError("Codex config rollback is invalid") from error
            candidate = candidate_text.encode()
            _atomic_cas(path, current, candidate)
            return
        before_hash = content_sha256(current)
        prepared = prepare_plugin_enabled(
            path, change.plugin_id, change.previous, expected_sha256=before_hash
        )
        candidate, _ = _candidate(current, change.plugin_id, change.previous)
        if prepared.before_sha256 != before_hash:
            raise CodexConfigError("rollback compare-and-swap precondition failed")
        _atomic_cas(path, current, candidate)


def observe_plugin_enabled_rollback(path: Path, change: PluginEnabledChange) -> str:
    """Classify a prepared rollback as completed, unapplied, or ambiguous."""
    _current, document = _load(path)
    plugins = document.get("plugins", {})
    if not isinstance(plugins, dict):
        return "ambiguous"
    table_exists = change.plugin_id in plugins
    if not table_exists:
        return "completed" if not change.table_existed else "ambiguous"
    plugin = plugins.get(change.plugin_id, {})
    if not isinstance(plugin, dict):
        return "ambiguous"
    observed = plugin.get("enabled")
    if not change.table_existed:
        return "unapplied" if observed is change.current else "ambiguous"
    if change.previous is None and "enabled" not in plugin:
        return "completed"
    if observed is change.previous:
        return "completed"
    if observed is change.current:
        return "unapplied"
    return "ambiguous"
