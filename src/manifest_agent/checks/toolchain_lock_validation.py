"""Structural validation for untrusted toolchain lock records."""

from collections.abc import Mapping

from . import toolchain
from .toolchain_provision import (
    _ENV_KINDS,
    _safe_artifact_url,
    _safe_component,
    _safe_relative,
    _valid_digest,
)


def validate_lock(lock: Mapping) -> None:
    """Reject malformed or unpinned lock records before touching the store."""
    _validate_top_level(lock)
    for bundle, entry in lock["tools"].items():
        _validate_tool_record(bundle, entry)
    _validate_cache_records(lock.get("caches", {}))


def _validate_top_level(lock: Mapping) -> None:
    if lock.get("schema_version") != 1 or not isinstance(lock.get("tools"), Mapping):
        raise ValueError("invalid toolchain lock schema")


def _validate_tool_record(bundle: object, entry: object) -> None:
    if not isinstance(bundle, str) or not toolchain._STORE_EXECUTABLE.match(
        f"store:{bundle}/bin/{bundle}"
    ):
        raise ValueError(f"invalid toolchain bundle name: {bundle!r}")
    if not isinstance(entry, Mapping) or not isinstance(
        entry.get("platforms"), Mapping
    ):
        raise ValueError(f"invalid toolchain entry: {bundle}")
    _validate_expected_version(bundle, entry)
    for platform, artifact in entry["platforms"].items():
        _validate_platform_record(bundle, entry, platform, artifact)


def _validate_expected_version(bundle: str, entry: Mapping) -> None:
    version = entry.get("version")
    if version is not None:
        version_is_safe = (
            _safe_relative(version)
            if entry.get("kind") in _ENV_KINDS
            else _safe_component(version)
        )
        if not version_is_safe:
            raise ValueError(f"invalid expected version for {bundle}")


def _validate_platform_record(
    bundle: str, entry: Mapping, platform: object, artifact: object
) -> None:
    if not _safe_component(platform) or not isinstance(artifact, Mapping):
        raise ValueError(f"invalid platform record for {bundle}")
    if not _safe_artifact_url(artifact.get("url")):
        raise ValueError(f"invalid artifact URL for {bundle}/{platform}")
    if not _safe_relative(str(artifact.get("path_in_archive", ""))):
        raise ValueError(f"unsafe archive path for {bundle}/{platform}")
    _validate_environment_pins(bundle, entry, platform, artifact)
    _validate_extra_executables(bundle, platform, artifact)
    _validate_artifact_digests(bundle, platform, artifact)


def _validate_environment_pins(
    bundle: str, entry: Mapping, platform: object, artifact: Mapping
) -> None:
    if (
        entry.get("kind") == "node-env"
        and artifact.get("package_json_sha256") is not None
        and not _valid_digest(artifact["package_json_sha256"])
    ):
        raise ValueError(f"invalid package_json_sha256 for {bundle}/{platform}")
    provider = artifact.get("python_provider")
    valid_provider = (
        isinstance(provider, Mapping)
        and all(
            isinstance(provider.get(field), str) and provider[field]
            for field in ("implementation", "version", "build")
        )
        and _valid_digest(provider.get("exe_sha256"))
    )
    if (
        entry.get("kind") == "python-env"
        and provider is not None
        and not valid_provider
    ):
        raise ValueError(f"invalid Python provider for {bundle}/{platform}")


def _validate_extra_executables(
    bundle: str, platform: object, artifact: Mapping
) -> None:
    extra = artifact.get("extra_executables") or {}
    if not isinstance(extra, Mapping):
        raise ValueError(f"invalid extra executables for {bundle}/{platform}")
    for name, spec in extra.items():
        if not _safe_component(name) or not isinstance(spec, Mapping):
            raise ValueError(f"invalid extra executable for {bundle}/{platform}")
        if not all(
            _safe_relative(str(spec.get(path_field, "")))
            for path_field in ("path_in_archive", "executable_relative")
        ):
            raise ValueError(f"unsafe extra executable path for {bundle}/{platform}")


def _validate_artifact_digests(
    bundle: str, platform: object, artifact: Mapping
) -> None:
    for digest_field in ("sha256", "exe_sha256"):
        digest = artifact.get(digest_field)
        if digest is not None and not _valid_digest(digest):
            raise ValueError(f"invalid {digest_field} for {bundle}/{platform}")


def _validate_cache_records(caches: object) -> None:
    if not isinstance(caches, Mapping):
        raise ValueError("invalid toolchain caches")
    for cache_name, cache_entry in caches.items():
        if not _safe_component(cache_name) or not isinstance(cache_entry, Mapping):
            raise ValueError("invalid toolchain cache entry")
        _validate_cache_platform_records(cache_name, cache_entry)


def _validate_cache_platform_records(cache_name: object, cache_entry: Mapping) -> None:
    platforms = cache_entry.get("platforms")
    if not isinstance(platforms, Mapping):
        raise ValueError(f"invalid cache platforms for {cache_name}")
    for platform, record in platforms.items():
        if not _safe_component(platform) or (
            record is not None and not isinstance(record, Mapping)
        ):
            raise ValueError(f"invalid cache platform record for {cache_name}")
