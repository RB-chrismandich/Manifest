"""Environment launcher and deterministic attestation contracts."""

from __future__ import annotations

import hashlib
import shutil
import sys
from pathlib import Path

import pytest

from manifest_agent.checks import toolchain_env, toolchain_provision_env
from manifest_agent.checks import toolchain_provision as provision


def _trusted_python_env(
    store: Path, checkout: Path, *, interpreter: Path | None = None
) -> tuple[Path, Path]:
    """Build a minimal installed Python environment without ambient state."""
    env_root = store / "tools" / "python-env" / "fixture"
    python = env_root / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.symlink_to(interpreter or Path(sys.executable))
    console = env_root / "bin" / "demo"
    console.write_text(f"#!{python}\nprint('demo')\n")
    console.chmod(0o755)
    pth = env_root / "lib" / "python3" / "site-packages" / "checkout.pth"
    pth.parent.mkdir(parents=True)
    pth.write_text(".\n")
    return env_root, console


def test_verify_env_exe_accepts_only_the_attested_python_launcher_role(
    tmp_path: Path,
):
    store = tmp_path / "store"
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    env_root, console = _trusted_python_env(store, checkout)
    digest = toolchain_env.distribution_set_digest(
        env_root, "python-env", store=store, checkout_root=checkout
    )
    trust = toolchain_env.EnvTrust(store, checkout)

    python = toolchain_env.verify_env_exe(
        "python-env",
        "python-env",
        {"path": "tools/python-env/fixture/bin/python"},
        trust,
        digest,
        None,
    )
    ordinary_console = toolchain_env.verify_env_exe(
        "python-env",
        "python-env",
        {"path": "tools/python-env/fixture/bin/demo"},
        trust,
        digest,
        None,
    )

    assert isinstance(python, toolchain_env.ResolvedTool)
    assert isinstance(ordinary_console, toolchain_env.ResolvedTool)
    assert ordinary_console.executable == console


def test_verify_env_exe_rejects_an_external_python_substitution(tmp_path: Path):
    store = tmp_path / "store"
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    env_root, console = _trusted_python_env(store, checkout)
    console.write_text(f"#!{Path(sys.executable)}\nprint('substituted')\n")
    console.chmod(0o755)
    digest = toolchain_env.distribution_set_digest(
        env_root, "python-env", store=store, checkout_root=checkout
    )

    result = toolchain_env.verify_env_exe(
        "python-env",
        "python-env",
        {"path": "tools/python-env/fixture/bin/demo"},
        toolchain_env.EnvTrust(store, checkout),
        digest,
        None,
    )

    assert result == toolchain_env.BlockedReason(
        "toolchain: python-env digest mismatch"
    )


def test_verify_env_exe_rejects_relocated_python_with_identical_bytes(tmp_path: Path):
    store = tmp_path / "store"
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    relocated = tmp_path / "python-relocated"
    shutil.copy2(Path(sys.executable), relocated)
    env_root, _console = _trusted_python_env(store, checkout, interpreter=relocated)

    with pytest.raises(ValueError, match="trusted Python provider"):
        toolchain_env.distribution_set_digest(
            env_root, "python-env", store=store, checkout_root=checkout
        )
    result = toolchain_env.verify_env_exe(
        "python-env",
        "python-env",
        {"path": "tools/python-env/fixture/bin/python"},
        toolchain_env.EnvTrust(store, checkout),
        "0" * 64,
        None,
    )

    assert result == toolchain_env.BlockedReason(
        "toolchain: python-env not provisioned (run manifest provision)"
    )


def test_environment_digests_normalize_only_generated_path_bearers(tmp_path: Path):
    first_store, second_store = tmp_path / "first-store", tmp_path / "second-store"
    first_checkout, second_checkout = (
        tmp_path / "first-checkout",
        tmp_path / "second-checkout",
    )
    (first_checkout / "src").mkdir(parents=True)
    (second_checkout / "src").mkdir(parents=True)
    first_root, first_console = _trusted_python_env(first_store, first_checkout)
    second_root, _second_console = _trusted_python_env(second_store, second_checkout)

    first = toolchain_env.distribution_set_digest(
        first_root, "python-env", store=first_store, checkout_root=first_checkout
    )
    second = toolchain_env.distribution_set_digest(
        second_root, "python-env", store=second_store, checkout_root=second_checkout
    )
    first_console.write_text(first_console.read_text().replace("demo", "changed"))
    first_console.chmod(0o755)

    assert first == second
    assert (
        toolchain_env.distribution_set_digest(
            first_root, "python-env", store=first_store, checkout_root=first_checkout
        )
        != first
    )


@pytest.mark.parametrize(
    "pth_contents",
    (
        "import sys; sys.path.insert(0, '/tmp/poison')\n",
        "/tmp/poison\n",
        "../../../../../../poison\n",
    ),
)
def test_environment_digest_rejects_pth_that_can_escape_environment(
    tmp_path: Path, pth_contents: str
):
    store = tmp_path / "store"
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    env_root, _console = _trusted_python_env(store, checkout)
    (env_root / "lib" / "python3" / "site-packages" / "checkout.pth").write_text(
        pth_contents
    )

    with pytest.raises(toolchain_env.UntrustedPthError):
        toolchain_env.distribution_set_digest(
            env_root, "python-env", store=store, checkout_root=checkout
        )


def test_environment_digest_rejects_changed_pyvenv_provider(tmp_path: Path):
    store = tmp_path / "store"
    checkout = tmp_path / "checkout"
    (checkout / "src").mkdir(parents=True)
    env_root, _console = _trusted_python_env(store, checkout)
    provider = Path(sys.executable).resolve()
    (env_root / "pyvenv.cfg").write_text(
        "\n".join(
            (
                f"home = {provider.parent}",
                f"executable = {provider}",
                f"command = {provider} -m venv {env_root}",
            )
        )
        + "\n"
    )
    toolchain_env.distribution_set_digest(
        env_root, "python-env", store=store, checkout_root=checkout
    )
    (env_root / "pyvenv.cfg").write_text(
        (env_root / "pyvenv.cfg")
        .read_text()
        .replace(str(provider), str(tmp_path / "untrusted-python"))
    )

    with pytest.raises(ValueError, match="pyvenv"):
        toolchain_env.distribution_set_digest(
            env_root, "python-env", store=store, checkout_root=checkout
        )


@pytest.mark.parametrize(
    ("pinned_digest", "reason"),
    [
        (None, "toolchain: env unattested for linux-x64"),
        ("0" * 64, "toolchain: env digest mismatch"),
    ],
)
def test_environment_provision_never_passes_missing_or_stale_digest_pins(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    pinned_digest: str | None,
    reason: str,
):
    source = b"environment lock bytes"
    (tmp_path / "source.lock").write_bytes(source)
    lock = {
        "schema_version": 1,
        "tools": {
            "env": {
                "kind": "node-env",
                "version": "config/toolchain/package.json",
                "platforms": {
                    "linux-x64": {
                        "url": "file://source.lock",
                        "sha256": hashlib.sha256(source).hexdigest(),
                        "exe_sha256": pinned_digest,
                        "path_in_archive": ".",
                        "console_scripts": ["bin/demo"],
                    }
                },
            }
        },
    }

    def materialize(_ctx, _bundle, _entry, env_root, _names):
        lock_file = env_root / "node_modules" / ".package-lock.json"
        lock_file.parent.mkdir(parents=True)
        lock_file.write_text('{"packages":{"node_modules/demo":{"version":"1"}}}')
        console = env_root / "node_modules" / ".bin" / "demo"
        console.parent.mkdir()
        console.write_text("#!/usr/bin/env node\n")
        console.chmod(0o755)
        return {"demo": Path("node_modules/.bin/demo")}

    monkeypatch.setattr(toolchain_provision_env, "_materialize_env", materialize)
    outcome = provision.provision(
        lock,
        tmp_path / "store",
        platform="linux-x64",
        repo_root=tmp_path,
    )[0]

    assert outcome.status == "blocked"
    assert outcome.reason == reason
    assert outcome.digest is not None
    assert len(outcome.digest) == 64
