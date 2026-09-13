"""Regression coverage for environment-tree attestation."""

from __future__ import annotations

from pathlib import Path

from manifest_agent.checks import toolchain_env_digest


def test_distribution_digest_tracks_non_normalized_payload_bytes(tmp_path: Path):
    """A package payload change must alter the attested environment digest."""
    env_root = tmp_path / "env"
    lock_file = env_root / "node_modules" / ".package-lock.json"
    lock_file.parent.mkdir(parents=True)
    lock_file.write_text('{"packages":{}}')
    payload = env_root / "node_modules" / "demo" / "index.js"
    payload.parent.mkdir()
    payload.write_text("module.exports = 'trusted';")

    before = toolchain_env_digest.distribution_set_digest(env_root, "node-env")
    payload.write_text("module.exports = 'changed';")
    assert toolchain_env_digest.distribution_set_digest(env_root, "node-env") != before


def test_staged_environment_digest_matches_published_environment(tmp_path: Path):
    """A relocated launcher has one digest before and after publishing."""
    published = tmp_path / "store" / "tools" / "env" / "digest"
    staged = tmp_path / "store" / "stage"
    for root, shebang_root in ((staged, published), (published, published)):
        launcher = root / "bin" / "demo"
        launcher.parent.mkdir(parents=True, exist_ok=True)
        launcher.write_text(f"#!{shebang_root / 'bin' / 'python'}\n")
        launcher.chmod(0o755)
        lock = root / "node_modules" / ".package-lock.json"
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text('{"packages":{}}')

    staged_digest = toolchain_env_digest.distribution_set_digest(
        staged, "node-env", canonical_env_root=published
    )
    published_digest = toolchain_env_digest.distribution_set_digest(
        published, "node-env"
    )

    assert staged_digest == published_digest


def _record_row(path: str, content: bytes) -> str:
    digest = (
        __import__("base64")
        .urlsafe_b64encode(__import__("hashlib").sha256(content).digest())
        .rstrip(b"=")
        .decode()
    )
    return f"{path},sha256={digest},{len(content)}"


def _record_environment(root: Path, checkout: Path) -> None:
    package = root / "lib" / "python3" / "site-packages" / "demo.py"
    package.parent.mkdir(parents=True)
    package.write_text("value = 'trusted'\n")
    direct_url = package.parent / "demo-1.0.dist-info" / "direct_url.json"
    direct_url.parent.mkdir()
    direct_url.write_text(f'{{"url":"file://{checkout}/demo"}}')
    record = direct_url.parent / "RECORD"
    record.write_text(
        "\n".join(
            (
                _record_row(package.relative_to(root).as_posix(), package.read_bytes()),
                _record_row(
                    direct_url.relative_to(root).as_posix(), direct_url.read_bytes()
                ),
                f"{record.relative_to(root).as_posix()},,",
            )
        )
        + "\n"
    )


def test_distribution_digest_canonicalizes_record_metadata_across_roots(
    tmp_path: Path,
):
    first_root, second_root = tmp_path / "first-env", tmp_path / "second-env"
    _record_environment(first_root, tmp_path / "first-checkout")
    _record_environment(second_root, tmp_path / "second-checkout")

    first = toolchain_env_digest.distribution_set_digest(
        first_root, "python-env", checkout_root=tmp_path / "first-checkout"
    )
    second = toolchain_env_digest.distribution_set_digest(
        second_root, "python-env", checkout_root=tmp_path / "second-checkout"
    )

    assert first == second


def test_distribution_digest_detects_record_owned_payload_mutation(tmp_path: Path):
    root = tmp_path / "env"
    checkout = tmp_path / "checkout"
    _record_environment(root, checkout)
    before = toolchain_env_digest.distribution_set_digest(
        root, "python-env", checkout_root=checkout
    )
    package = root / "lib" / "python3" / "site-packages" / "demo.py"
    package.write_text("value = 'substituted'\n")

    assert (
        toolchain_env_digest.distribution_set_digest(
            root, "python-env", checkout_root=checkout
        )
        != before
    )
