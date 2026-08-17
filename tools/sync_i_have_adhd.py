#!/usr/bin/env python3
"""Verify or refresh the reviewed i-have-adhd mirror from one Git object."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

UPSTREAM_REPOSITORY = "https://github.com/ayghri/i-have-adhd"
MIRRORED_FILES = {
    "skills/i-have-adhd/SKILL.md": "skills/i-have-adhd/SKILL.md",
    "LICENSE.upstream": "LICENSE",
}


class SyncError(RuntimeError):
    """The pinned source or mirror cannot be verified safely."""


@dataclass(frozen=True)
class UpstreamLock:
    repository: str
    commit: str
    license: str
    files: dict[str, str]
    synced_at: str


@dataclass(frozen=True)
class SyncResult:
    changed: bool
    lock: UpstreamLock


def load_upstream_lock(path: Path) -> UpstreamLock:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        lock = UpstreamLock(**value)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise SyncError("unable to read upstream provenance lock") from error
    if lock.repository != UPSTREAM_REPOSITORY or lock.license != "MIT":
        raise SyncError("upstream provenance identity is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", lock.commit) is None:
        raise SyncError("upstream lock must pin a full Git commit")
    if set(lock.files) != set(MIRRORED_FILES):
        raise SyncError("upstream lock contains an unexpected file set")
    if any(
        re.fullmatch(r"[0-9a-f]{64}", digest) is None for digest in lock.files.values()
    ):
        raise SyncError("upstream lock contains an invalid checksum")
    return lock


def verify_mirror(bundle: Path, lock: UpstreamLock) -> None:
    for relative, expected in lock.files.items():
        try:
            content = (bundle / relative).read_bytes()
        except OSError as error:
            raise SyncError(f"missing mirrored file: {relative}") from error
        if hashlib.sha256(content).hexdigest() != expected:
            raise SyncError(f"checksum mismatch for {relative}")
    skill = (bundle / "skills/i-have-adhd/SKILL.md").read_bytes()
    guidance_path = bundle / "guidance/always-on.md"
    try:
        guidance = guidance_path.read_bytes()
    except OSError as error:
        raise SyncError("missing generated ADHD guidance") from error
    if guidance != _guidance(skill):
        raise SyncError("generated ADHD guidance does not match canonical skill")


def _git(source: Path, *args: str, text: bool = True):
    result = subprocess.run(
        ("git", "-C", str(source), *args),
        check=False,
        capture_output=True,
        text=text,
    )
    if result.returncode != 0:
        raise SyncError("unable to read pinned upstream Git object")
    return result.stdout


def _object(source: Path, commit: str, path: str) -> bytes:
    mode_line = _git(source, "ls-tree", commit, "--", path).strip()
    parts = mode_line.split(maxsplit=3)
    if len(parts) != 4 or parts[0] != "100644" or parts[1] != "blob":
        raise SyncError(f"upstream path is not a regular file: {path}")
    return _git(source, "show", f"{commit}:{path}", text=False)


def _write_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _guidance(skill: bytes) -> bytes:
    text = skill.decode("utf-8")
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end < 0:
            raise SyncError("upstream skill has unterminated frontmatter")
        text = text[end + 5 :]
    return text.lstrip().encode("utf-8")


def _normalized_remote(url: str) -> str | None:
    """Reduce a Git remote URL to host/path so clone forms compare equal.

    The same repository is legitimately cloned as https://, git@host:path, or
    ssh://; comparing raw strings would reject an honest SSH clone.

    Returns None for anything that is not a recognized remote URL form. A bare
    filesystem path must never normalize into a host/path string: a local
    directory literally named `github.com/ayghri/i-have-adhd` would otherwise
    compare equal to the upstream and defeat the provenance check entirely,
    which is exactly the substitution this function exists to prevent.
    """
    value = url.strip().rstrip("/").removesuffix(".git")
    lowered = value.lower()
    for scheme in ("https://", "http://", "ssh://", "git://"):
        if lowered.startswith(scheme):
            value = value[len(scheme) :]
            break
    else:
        # scp-like form: [user@]host:path. The user@ is optional in git, so a
        # bare `github.com:owner/repo` is legitimate; only require that when an
        # "@" IS present it precedes the ":", so a path with a stray colon
        # cannot masquerade as a host.
        at = value.find("@")
        colon = value.find(":")
        if colon < 0:
            return None
        if at >= 0 and colon < at:
            return None
        value = value[at + 1 :] if at >= 0 else value
        value = value.replace(":", "/", 1)
    head, _, rest = value.partition("/")
    if "@" in head:
        head = head.split("@", 1)[1]
    # An explicit port is a transport detail, not a different repository:
    # ssh://git@github.com:22/owner/repo is the same upstream as the https URL.
    host, sep, port = head.rpartition(":")
    if sep and port.isdigit():
        head = host
    if not head or not rest:
        return None
    return f"{head}/{rest}".lower()


def _assert_upstream_origin(source: Path) -> None:
    """Confirm --source really is the upstream this tool claims to mirror.

    The commit pin and checksums only prove the lock matches whatever bytes
    were copied -- they cannot show the bytes came from UPSTREAM_REPOSITORY.
    Without this, pointing --source at any local clone stamps a false
    provenance claim into upstream-lock.json that --check then re-verifies
    against itself.

    Every configured remote is considered, not only one named "origin", and
    URLs compare in normalized host/path form so an SSH clone of the real
    upstream is accepted. A deliberate fork is still rejected: mirroring it
    would stamp the upstream URL onto bytes that did not come from upstream.
    """
    expected = _normalized_remote(UPSTREAM_REPOSITORY)
    assert expected is not None  # UPSTREAM_REPOSITORY is a well-formed https URL
    listed = _git(source, "remote").split()
    if not listed:
        raise SyncError(
            f"--source has no Git remote to verify against {UPSTREAM_REPOSITORY!r}"
        )
    observed = []
    for name in listed:
        url = _git(source, "remote", "get-url", name).strip()
        normalized = _normalized_remote(url)
        if normalized is not None and normalized == expected:
            return
        observed.append(f"{name}={url}")
    raise SyncError(
        f"--source remotes ({', '.join(observed)}) do not match {UPSTREAM_REPOSITORY!r}"
    )


def sync_upstream(
    source: Path,
    bundle: Path,
    *,
    commit: str | None = None,
    apply: bool = False,
) -> SyncResult:
    _assert_upstream_origin(source)
    pinned = commit or _git(source, "rev-parse", "HEAD").strip()
    if re.fullmatch(r"[0-9a-f]{40}", pinned) is None:
        raise SyncError("--commit must be a full Git commit")
    if _git(source, "cat-file", "-t", pinned).strip() != "commit":
        raise SyncError("pinned upstream object is not a commit")
    content = {
        destination: _object(source, pinned, upstream)
        for destination, upstream in MIRRORED_FILES.items()
    }
    synced_at = _git(source, "show", "-s", "--format=%cI", pinned).strip()[:10]
    lock = UpstreamLock(
        repository=UPSTREAM_REPOSITORY,
        commit=pinned,
        license="MIT",
        files={
            path: hashlib.sha256(data).hexdigest() for path, data in content.items()
        },
        synced_at=synced_at,
    )
    lock_bytes = (json.dumps(lock.__dict__, indent=2, sort_keys=True) + "\n").encode()
    changed = (
        any(
            not (bundle / path).exists() or (bundle / path).read_bytes() != data
            for path, data in content.items()
        )
        or not (bundle / "upstream-lock.json").exists()
        or (bundle / "upstream-lock.json").read_bytes() != lock_bytes
        or not (bundle / "guidance/always-on.md").exists()
        or (bundle / "guidance/always-on.md").read_bytes()
        != _guidance(content["skills/i-have-adhd/SKILL.md"])
    )
    if apply:
        for path, data in content.items():
            _write_atomic(bundle / path, data)
        _write_atomic(
            bundle / "guidance/always-on.md",
            _guidance(content["skills/i-have-adhd/SKILL.md"]),
        )
        _write_atomic(bundle / "upstream-lock.json", lock_bytes)
    return SyncResult(changed, lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument(
        "--bundle", type=Path, default=Path("plugins/manifest-i-have-adhd")
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = sync_upstream(
            args.source, args.bundle, commit=args.commit, apply=args.apply
        )
    except SyncError as error:
        print(f"sync_i_have_adhd.py: {error}")
        return 2
    print(json.dumps(result.lock.__dict__, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
