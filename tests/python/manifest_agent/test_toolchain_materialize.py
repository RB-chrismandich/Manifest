"""Behavioral contracts for toolchain environment materialization helpers."""

import hashlib
from pathlib import Path

import pytest

from manifest_agent.checks import toolchain_materialize, toolchain_provision_env
from manifest_agent.checks.toolchain_materialize import MaterializationError, load_json
from manifest_agent.checks.toolchain_provision_models import ProvisionContext


def test_load_json_rejects_non_object_documents(tmp_path: Path) -> None:
    """Toolchain materialization rejects JSON that cannot supply named fields."""
    path = tmp_path / "array.json"
    path.write_text("[]", encoding="utf-8")

    with pytest.raises(MaterializationError, match="JSON object required"):
        load_json(path)


@pytest.mark.parametrize(
    ("bundle", "source_relative", "changed_relative"),
    [
        ("python-env", "config/toolchain/uv.lock", "config/pyproject.toml"),
        ("config-env", "configs/claude/uv.lock", "configs/pyproject.toml"),
        ("config-env", "configs/claude/uv.lock", "pyproject.toml"),
    ],
)
def test_python_env_rejects_changed_project_metadata_before_materialization(
    tmp_path: Path,
    monkeypatch,
    bundle: str,
    source_relative: str,
    changed_relative: str,
) -> None:
    repo_root = tmp_path / "repo"
    files = {
        "pyproject.toml": "[project]\nname = 'root'\n",
        "uv.lock": "root-locked",
        "config/toolchain/pyproject.toml": "[project]\nname = 'toolchain'\n",
        "config/toolchain/uv.lock": "toolchain-locked",
        "configs/claude/pyproject.toml": "[project]\nname = 'config'\n",
        "configs/claude/uv.lock": "config-locked",
        "configs/claude/scripts/manifest_model_policy/pyproject.toml": (
            "[project]\nname = 'policy'\n"
        ),
    }
    for relative, content in files.items():
        path = repo_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    source = (repo_root / source_relative).read_bytes()
    pinned = toolchain_materialize.python_project_metadata_digest(repo_root, bundle)
    (repo_root / changed_relative).write_text(
        "[tool.uv.workspace]\nmembers = ['config/toolchain']\n"
    )

    monkeypatch.setattr(
        toolchain_provision_env, "_read_source_bytes", lambda *_args: source
    )
    monkeypatch.setattr(
        toolchain_provision_env,
        "_materialize_attested",
        lambda *_args: pytest.fail("materialized before project metadata check"),
    )
    ctx = ProvisionContext(
        store=tmp_path / "store",
        lock={},
        platform="linux-x64",
        repo_root=repo_root,
    )
    platform_entry = {
        "url": f"file://{source_relative}",
        "sha256": hashlib.sha256(source).hexdigest(),
        "project_sha256": pinned,
    }

    outcome = toolchain_provision_env.provision_environment(
        ctx, bundle, {"kind": "python-env"}, platform_entry
    )

    assert outcome.status == "blocked"
    assert outcome.reason == f"toolchain: {bundle} project metadata digest mismatch"


@pytest.mark.parametrize(
    ("build_from_locked_environment", "expected"),
    [
        (
            True,
            [
                [
                    "--no-config",
                    "--locked",
                    "--no-dev",
                    "--no-editable",
                    "--no-install-project",
                    "--no-build",
                ],
                [
                    "--no-config",
                    "--locked",
                    "--no-dev",
                    "--no-editable",
                    "--no-build-isolation",
                ],
            ],
        ),
        (
            False,
            [["--no-config", "--locked", "--no-dev", "--no-editable"]],
        ),
    ],
)
def test_materialize_python_env_locked_build_sync_argv(
    tmp_path: Path,
    monkeypatch,
    build_from_locked_environment: bool,
    expected: list[list[str]],
) -> None:
    project = tmp_path / "config/toolchain"
    project.mkdir(parents=True)
    uv = tmp_path / "store/bin/uv"
    provider = tmp_path / "python"
    env_root = tmp_path / "env"
    monkeypatch.setattr(toolchain_materialize, "_resolved_uv", lambda _: uv)
    monkeypatch.setattr(toolchain_materialize, "_trusted_python", lambda _: provider)
    calls: list[list[str]] = []
    monkeypatch.setattr(
        toolchain_materialize,
        "_run",
        lambda argv, **kwargs: calls.append(argv),
    )
    monkeypatch.setattr(
        toolchain_materialize, "_remove_virtualenv_bootstrap_pth", lambda _: None
    )
    context = toolchain_materialize.MaterializeContext(
        lock={},
        store=tmp_path / "store",
        platform="linux-test",
        repo_root=tmp_path,
        env={},
    )

    toolchain_materialize.materialize_python_env(
        context, env_root, build_from_locked_environment=build_from_locked_environment
    )

    assert len(calls) == len(expected)
    assert calls == [
        [
            str(uv),
            "sync",
            *flags,
            "--python",
            str(provider),
            "--project",
            str(project),
        ]
        for flags in expected
    ]
    assert [
        argv[2 : 2 + len(flags)] for argv, flags in zip(calls, expected, strict=True)
    ] == expected
    assert all(argv[0] == str(uv) and argv[1] == "sync" for argv in calls)
    assert all("--no-config" in argv and "--locked" in argv for argv in calls)
    assert all(not any("pip" in arg.casefold() for arg in argv) for argv in calls)
