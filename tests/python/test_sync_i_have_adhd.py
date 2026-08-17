from pathlib import Path

import pytest

from tools.sync_i_have_adhd import (
    SyncError,
    _normalized_remote,
    load_upstream_lock,
    sync_upstream,
    verify_mirror,
)


def test_repository_lock_pins_exact_commit() -> None:
    repo_root = Path.cwd()
    lock = load_upstream_lock(
        repo_root / "plugins/manifest-i-have-adhd/upstream-lock.json"
    )
    assert lock.commit == "2d19ad205eb1d85fc9c3968bdeba4c2116518685"
    verify_mirror(repo_root / "plugins/manifest-i-have-adhd", lock)


def test_changed_mirror_is_rejected(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    bundle = tmp_path / "bundle"
    (bundle / "skills/i-have-adhd").mkdir(parents=True)
    (bundle / "skills/i-have-adhd/SKILL.md").write_text("changed")
    (bundle / "LICENSE.upstream").write_text("changed")
    lock = load_upstream_lock(
        repo_root / "plugins/manifest-i-have-adhd/upstream-lock.json"
    )
    with pytest.raises(SyncError, match="checksum"):
        verify_mirror(bundle, lock)


def test_guidance_only_drift_is_rejected(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    source = repo_root / "plugins/manifest-i-have-adhd"
    bundle = tmp_path / "bundle"
    (bundle / "skills/i-have-adhd").mkdir(parents=True)
    (bundle / "guidance").mkdir()
    for relative in ("skills/i-have-adhd/SKILL.md", "LICENSE.upstream"):
        target = bundle / relative
        target.write_bytes((source / relative).read_bytes())
    (bundle / "guidance/always-on.md").write_text("drifted\n", encoding="utf-8")
    lock = load_upstream_lock(source / "upstream-lock.json")

    with pytest.raises(SyncError, match="guidance"):
        verify_mirror(bundle, lock)


def test_sync_refuses_a_source_that_is_not_the_claimed_upstream(tmp_path):
    """Provenance must be verified, not asserted.

    The commit pin and checksums only prove the lock matches the bytes that
    were copied. Without an origin check, any local clone can be mirrored and
    stamped with the upstream URL, and --check re-verifies that against itself.
    """
    import subprocess

    source = tmp_path / "impostor"
    source.mkdir()
    subprocess.run(("git", "init", "-q", str(source)), check=True)
    subprocess.run(
        (
            "git",
            "-C",
            str(source),
            "remote",
            "add",
            "origin",
            "https://github.com/attacker/not-upstream",
        ),
        check=True,
    )

    with pytest.raises(SyncError, match="do not match"):
        sync_upstream(source, tmp_path / "bundle")


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/ayghri/i-have-adhd",
        "https://github.com/ayghri/i-have-adhd.git",
        "git@github.com:ayghri/i-have-adhd.git",
        "ssh://git@github.com/ayghri/i-have-adhd.git",
        "ssh://git@github.com:22/ayghri/i-have-adhd.git",  # explicit port
        "github.com:ayghri/i-have-adhd",  # scp form, no user@
        "HTTPS://github.com/ayghri/i-have-adhd",  # scheme is case-insensitive
    ],
)
def test_every_clone_form_of_the_real_upstream_is_accepted(url):
    """An honest SSH clone must not be rejected as the wrong repository."""
    from tools.sync_i_have_adhd import UPSTREAM_REPOSITORY

    assert _normalized_remote(url) == _normalized_remote(UPSTREAM_REPOSITORY)


def test_sync_accepts_upstream_under_a_non_origin_remote_name(tmp_path):
    """Remotes are not always named "origin"; verify by URL, not by name."""
    import subprocess

    source = tmp_path / "clone"
    source.mkdir()
    subprocess.run(("git", "init", "-q", str(source)), check=True)
    subprocess.run(
        (
            "git",
            "-C",
            str(source),
            "remote",
            "add",
            "upstream",
            "git@github.com:ayghri/i-have-adhd.git",
        ),
        check=True,
    )

    # Passes the origin gate, then fails later for an unrelated reason (no
    # commits) -- proving the provenance check itself did not reject it.
    with pytest.raises(SyncError) as caught:
        sync_upstream(source, tmp_path / "bundle")
    assert "do not match" not in str(caught.value)


def test_sync_rejects_a_source_with_no_remote_at_all(tmp_path):
    import subprocess

    source = tmp_path / "bare"
    source.mkdir()
    subprocess.run(("git", "init", "-q", str(source)), check=True)

    with pytest.raises(SyncError, match="no Git remote"):
        sync_upstream(source, tmp_path / "bundle")


@pytest.mark.parametrize(
    "url",
    [
        "github.com/ayghri/i-have-adhd",  # bare path that LOOKS like the URL
        "C:/github.com/ayghri/i-have-adhd",  # windows drive path
        "./x:github.com/ayghri/i-have-adhd",  # relative path containing a colon
        "file:///github.com/ayghri/i-have-adhd",
        "a:github.com/ayghri/i-have-adhd",  # colon-to-slash must not fabricate the host
        "/tmp/github.com/ayghri/i-have-adhd",  # absolute local path
        "./github.com/ayghri/i-have-adhd",  # relative local path
        "https://evil.com/github.com/ayghri/i-have-adhd",
        "git@evil.com:ayghri/i-have-adhd.git",
        "https://github.com.evil.com/ayghri/i-have-adhd",
    ],
)
def test_non_upstream_remotes_never_normalize_to_the_upstream(url):
    """A local directory named like the upstream must not pass as provenance.

    Without a form check, a bare path normalizes to the same host/path string
    as the real URL, so `git remote add origin ./github.com/ayghri/i-have-adhd`
    would defeat the provenance guarantee entirely.
    """
    from tools.sync_i_have_adhd import UPSTREAM_REPOSITORY

    assert _normalized_remote(url) != _normalized_remote(UPSTREAM_REPOSITORY)


def test_sync_rejects_a_local_path_remote_named_like_the_upstream(tmp_path):
    import subprocess

    source = tmp_path / "impostor"
    source.mkdir()
    subprocess.run(("git", "init", "-q", str(source)), check=True)
    subprocess.run(
        (
            "git",
            "-C",
            str(source),
            "remote",
            "add",
            "origin",
            "github.com/ayghri/i-have-adhd",
        ),
        check=True,
    )

    with pytest.raises(SyncError, match="do not match"):
        sync_upstream(source, tmp_path / "bundle")
