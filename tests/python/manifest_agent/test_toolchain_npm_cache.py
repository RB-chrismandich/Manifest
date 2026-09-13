"""Regression contracts for deterministic npm cacache attestation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from manifest_agent.checks import toolchain_npm_cache


def _cache(
    root: Path,
    *,
    index_relative: Path | None = None,
    content_bytes: bytes,
    payload: dict[str, object],
    checksum: bytes | None = None,
) -> Path:
    """Create one minimal valid cacache lookup and its content payload."""
    key = payload["key"]
    assert isinstance(key, str)
    key_digest = hashlib.sha256(key.encode()).hexdigest()
    index = (
        root
        / "_cacache"
        / "index-v5"
        / (index_relative or Path(key_digest[:2]) / key_digest[2:4] / key_digest[4:])
    )
    content = root / "_cacache" / "content-v2" / "sha512" / "bb"
    index.parent.mkdir(parents=True)
    content.mkdir(parents=True)
    content.joinpath("payload").write_bytes(content_bytes)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    index.write_bytes(
        (checksum or hashlib.sha1(raw).hexdigest().encode()) + b"\t" + raw + b"\n"
    )
    return root


def test_npm_cache_digest_accepts_cacache_sha1_and_ignores_volatile_index_data(
    tmp_path: Path,
) -> None:
    """Equivalent downloads preserve their lookup bucket but ignore HTTP dates."""
    first = _cache(
        tmp_path / "first",
        index_relative=None,
        content_bytes=b"payload",
        payload={
            "key": "make-fetch-happen:request-cache:https://registry.example/pkg",
            "integrity": "sha512-x",
            "size": 7,
            "time": 1,
            "metadata": {
                "date": "Mon, 01 Jan 2024 00:00:00 GMT",
                "expires": "Mon, 01 Jan 2024 00:00:00 GMT",
                "time": 2,
            },
        },
    )
    second = _cache(
        tmp_path / "second",
        index_relative=None,
        content_bytes=b"payload",
        payload={
            "key": "make-fetch-happen:request-cache:https://registry.example/pkg",
            "integrity": "sha512-x",
            "size": 7,
            "time": 3,
            "metadata": {
                "date": "Tue, 02 Jan 2024 00:00:00 GMT",
                "expires": "Tue, 02 Jan 2024 00:00:00 GMT",
                "time": 4,
            },
        },
    )

    assert toolchain_npm_cache.index_digest(first) == toolchain_npm_cache.index_digest(
        second
    )


def test_npm_cache_digest_rejects_tampered_cacache_lookup(tmp_path: Path) -> None:
    """A hashEntry checksum must authenticate the unmodified raw record bytes."""
    cache = _cache(
        tmp_path / "cache",
        index_relative=None,
        content_bytes=b"payload",
        payload={"integrity": "sha512-x", "key": "pkg", "size": 7},
        checksum=b"0" * 40,
    )

    with pytest.raises(toolchain_npm_cache.NpmCacheError, match="malformed index"):
        toolchain_npm_cache.index_digest(cache)


def test_npm_cache_digest_changes_for_tampered_content(tmp_path: Path) -> None:
    """Cache content bytes remain part of the attested semantic digest."""
    payload = {"integrity": "sha512-x", "key": "pkg", "size": 7}
    expected = _cache(
        tmp_path / "expected",
        index_relative=None,
        content_bytes=b"payload",
        payload=payload,
    )
    tampered = _cache(
        tmp_path / "tampered",
        index_relative=None,
        content_bytes=b"tampered",
        payload=payload,
    )

    assert toolchain_npm_cache.index_digest(
        expected
    ) != toolchain_npm_cache.index_digest(tampered)


def test_npm_cache_digest_rejects_misbucketed_cacache_lookup(tmp_path: Path) -> None:
    """A cache index record must live in the bucket derived from its key."""
    cache = _cache(
        tmp_path / "cache",
        index_relative=Path("aa") / "bb" / "wrong",
        content_bytes=b"payload",
        payload={"integrity": "sha512-x", "key": "pkg", "size": 7},
    )

    with pytest.raises(toolchain_npm_cache.NpmCacheError, match="malformed index"):
        toolchain_npm_cache.index_digest(cache)


def test_attestation_observes_unpinned_cache_without_recording(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = SimpleNamespace(
        lock={
            "caches": {
                "node-cache": {
                    "source_sha256": "source",
                    "platforms": {"linux-x64": {"digest": None}},
                }
            }
        },
        platform="linux-x64",
        repo_root=tmp_path,
        attest_missing=True,
    )
    monkeypatch.setattr(toolchain_npm_cache, "source_sha256", lambda _root: "source")
    monkeypatch.setattr(
        toolchain_npm_cache,
        "materialize",
        lambda *_args, **kwargs: (
            (_ for _ in ()).throw(AssertionError("must remain ephemeral"))
            if kwargs["publish"]
            else (tmp_path / "stage", "a" * 64)
        ),
    )

    assert toolchain_npm_cache.provision(ctx, "node-cache") == (
        "UNPINNED",
        "UNPINNED: toolchain: node-cache unattested",
        "a" * 64,
    )
