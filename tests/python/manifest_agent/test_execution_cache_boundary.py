"""Real-child regressions for per-execution cache and store isolation."""

from __future__ import annotations

import hashlib
import json
import os
import venv
from pathlib import Path

import pytest

from manifest_agent.checks import toolchain
from manifest_agent.checks.models import Candidate, CheckSpec
from manifest_agent.checks.runner import execute_check
from manifest_agent.checks.toolchain_env_digest import (
    distribution_set_digest,
    trusted_python_provider,
)


def _snapshot(root):
    return {
        p.relative_to(root).as_posix(): (
            p.lstat().st_mode,
            p.readlink().as_posix()
            if p.is_symlink()
            else p.read_bytes()
            if p.is_file()
            else None,
        )
        for p in root.rglob("*")
    }


def _fixture_store(store: Path, candidate: Path):
    environment = store / "tools/project-env/fixture"
    venv.EnvBuilder(with_pip=False, symlinks=True).create(environment)
    # CPython 3.14 can add this optional alias; it is not a pinned launcher role.
    (environment / "bin" / "𝜋thon").unlink(missing_ok=True)
    provider = trusted_python_provider().lock_record()
    tree = distribution_set_digest(
        environment,
        "python-env",
        store=store,
        checkout_root=candidate,
        python_provider=provider,
    )
    platform = toolchain.current_platform()
    artifact = {
        "url": "file://uv.lock",
        "sha256": hashlib.sha256(b"fixture").hexdigest(),
        "exe_sha256": tree,
        "console_scripts": ["bin/python"],
        "python_provider": provider,
    }
    lock = {
        "schema_version": 1,
        "tools": {
            "project-env": {
                "kind": "python-env",
                "version": "fixture",
                "platforms": {platform: artifact},
            }
        },
    }
    manifest = {
        "schema_version": 1,
        "platform": platform,
        "lock_digest": toolchain.lock_digest(lock),
        "tools": {
            "project-env": {
                "version": "fixture",
                "platform": platform,
                "source": artifact["url"],
                "source_sha256": artifact["sha256"],
                "executables": {
                    "bin/python": {"path": "tools/project-env/fixture/bin/python"}
                },
            }
        },
    }
    (store / "manifest.json").write_text(json.dumps(manifest))
    return lock, environment, tree, provider


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("exit_code", [0, 7])
def test_two_real_runs_reuse_original_attested_store_without_bytecode_mutation(
    tmp_path, explicit, exit_code
):
    arguments = _real_run_arguments(tmp_path, explicit, exit_code)
    _assert_two_real_runs(*arguments, exit_code)


def _real_run_arguments(tmp_path, explicit, exit_code):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "sample.py").write_text("value = 42\n")
    (candidate / "check.py").write_text(
        "import json, os, pathlib, py_compile, sys, sample\n"
        "assert sample.value == 42\n"
        "py_compile.compile(sample.__file__, doraise=True)\n"
        "with open(os.environ['TRACE'], 'a') as stream:\n"
        "    stream.write(json.dumps({'store': os.environ['MANIFEST_TOOLCHAIN_STORE'], "
        "'cache': os.environ['MANIFEST_RUN_TMP']}) + '\\n')\n"
        f"raise SystemExit({exit_code})\n"
    )
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "MANIFEST_TOOLCHAIN_STORE",
            "PYTHONDONTWRITEBYTECODE",
            "PYTHONPYCACHEPREFIX",
        }
    }
    env.update(
        XDG_CACHE_HOME=str(tmp_path / "cache"),
        PYTHONPATH=str(candidate),
        TRACE=str(tmp_path / "trace"),
    )
    if explicit:
        env["MANIFEST_TOOLCHAIN_STORE"] = str(tmp_path / "explicit-store")
    store = toolchain.store_root(env, candidate)
    lock, environment, expected, provider = _fixture_store(store, candidate)
    registry = {
        "toolchain_lock_document": lock,
        "toolchain_lock_digest": toolchain.lock_digest(lock),
    }
    check = CheckSpec(
        "real",
        "test",
        "test",
        ("store:project-env/bin/python", "check.py"),
        ".",
        ("sample.py",),
        (),
        30,
        "all",
        "python",
        "fixture",
    )
    return (
        candidate,
        store,
        env,
        lock,
        environment,
        expected,
        provider,
        registry,
        check,
    )


def _assert_two_real_runs(
    candidate,
    store,
    env,
    lock,
    environment,
    expected,
    provider,
    registry,
    check,
    exit_code,
):
    before_candidate, before_store = _snapshot(candidate), _snapshot(store)
    for _ in range(2):
        result = execute_check(
            check, Candidate(candidate, "digest", "head", "tree"), env, registry
        )
        assert result.status == ("PASS" if exit_code == 0 else "FAIL"), (
            result.diagnostics
        )
        resolved = toolchain.resolve(
            "store:project-env/bin/python",
            lock=lock,
            store=store,
            platform=toolchain.current_platform(),
            repo_root=candidate,
        )
        assert isinstance(resolved, toolchain.ResolvedTool)
        assert (
            distribution_set_digest(
                environment,
                "python-env",
                store=store,
                checkout_root=candidate,
                python_provider=provider,
            )
            == expected
        )
        assert _snapshot(candidate) == before_candidate
        assert _snapshot(store) == before_store
    traces = [json.loads(line) for line in Path(env["TRACE"]).read_text().splitlines()]
    assert [entry["store"] for entry in traces] == [str(store), str(store)]
    assert traces[0]["cache"] != traces[1]["cache"]
    assert all(not Path(entry["cache"]).exists() for entry in traces)


def test_unsafe_candidate_store_blocks_before_real_child(tmp_path):
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    check = CheckSpec(
        "unsafe",
        "test",
        "test",
        ("python3", "-c", "raise AssertionError('executed')"),
        ".",
        (),
        (),
        30,
        "all",
        "python",
        "fixture",
    )
    result = execute_check(
        check,
        Candidate(candidate, "d", "h", "t"),
        {"MANIFEST_TOOLCHAIN_STORE": str(candidate / "store")},
    )
    assert result.status == "BLOCKED"
    assert not (candidate / "store").exists()
