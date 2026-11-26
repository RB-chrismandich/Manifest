"""Python materialization and staged-directory hardening regressions."""

from __future__ import annotations

from pathlib import Path

import pytest

from manifest_agent.checks import toolchain_env_digest, toolchain_materialize
from manifest_agent.checks import toolchain_provision_store as store_mutations


def test_uncommitted_stage_is_discarded_instead_of_published(tmp_path: Path):
    store = tmp_path / "store"
    relative = "tools/demo/digest"

    with store_mutations.staged_directory(store, relative) as transaction:
        (transaction.path / "payload").write_text("unverified")

    assert not (store / relative).exists()


@pytest.mark.parametrize(
    ("materialize", "expected_flag"),
    [
        (toolchain_materialize.materialize_python_env, "--locked"),
        (toolchain_materialize.materialize_project_env, "--frozen"),
    ],
)
def test_python_materializers_install_local_dependencies_non_editably(
    tmp_path: Path, monkeypatch, materialize, expected_flag: str
):
    """Both uv sync paths must materialize path dependencies, never link them."""
    repo_root = tmp_path / "repo"
    (repo_root / "config/toolchain").mkdir(parents=True)
    calls: list[list[str]] = []
    environments: list[dict[str, str]] = []
    virtualenv_pth = tmp_path / "env/lib/python3/site-packages/_virtualenv.pth"

    def record_sync(argv, **kwargs):
        calls.append(argv)
        environments.append(kwargs["env"])
        virtualenv_pth.parent.mkdir(parents=True)
        virtualenv_pth.write_text("import _virtualenv\n")

    monkeypatch.setattr(
        toolchain_materialize, "_resolved_uv", lambda _ctx: tmp_path / "uv"
    )
    monkeypatch.setattr(toolchain_materialize, "_run", record_sync)

    materialize(
        toolchain_materialize.MaterializeContext(
            {},
            tmp_path / "store",
            "linux-x64",
            repo_root,
            {},
            toolchain_env_digest.trusted_python_provider().lock_record(),
        ),
        tmp_path / "env",
    )

    assert expected_flag in calls[0]
    assert "--no-config" in calls[0]
    assert "--no-editable" in calls[0]
    assert environments[0]["UV_LINK_MODE"] == "copy"
    assert not virtualenv_pth.exists()


def test_python_materializer_rejects_modified_virtualenv_bootstrap(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / "config/toolchain").mkdir(parents=True)
    virtualenv_pth = tmp_path / "env/lib/python3/site-packages/_virtualenv.pth"

    def write_modified_bootstrap(_argv, **_kwargs):
        virtualenv_pth.parent.mkdir(parents=True)
        virtualenv_pth.write_text("import attacker_controlled\n")

    monkeypatch.setattr(
        toolchain_materialize, "_resolved_uv", lambda _ctx: tmp_path / "uv"
    )
    monkeypatch.setattr(toolchain_materialize, "_run", write_modified_bootstrap)

    with pytest.raises(
        toolchain_materialize.MaterializationError,
        match="unexpected virtualenv bootstrap",
    ):
        toolchain_materialize.materialize_python_env(
            toolchain_materialize.MaterializeContext(
                {},
                tmp_path / "store",
                "linux-x64",
                repo_root,
                {},
                toolchain_env_digest.trusted_python_provider().lock_record(),
            ),
            tmp_path / "env",
        )
