"""Temporary-sentinel regressions for both shipped smoke catalog runtimes."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RUNTIMES = [
    ROOT / "configs/claude/scripts/smoke_orchestrator",
    ROOT
    / "plugins/manifest-code-quality/skills/smoke-manage/scripts/smoke_orchestrator",
]


@pytest.fixture(params=RUNTIMES, ids=["legacy", "plugin"])
def runtime(request):
    """Load each real package separately so a cached module cannot mask drift."""
    name = f"smoke_lock_{RUNTIMES.index(request.param)}"
    spec = importlib.util.spec_from_file_location(name, request.param / "__init__.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return importlib.import_module(f"{name}.appender")


def workflow(test_id="sample"):
    """A valid ordinary catalog update."""
    return {
        "app": "demo",
        "id": test_id,
        "tier": "Lite",
        "steps": [
            {"name": "health", "type": "api", "method": "GET", "path": "/health"}
        ],
    }


def mutate(runtime, directory, operation):
    """Exercise the public mutation API, including its nominal no-op paths."""
    appender = runtime.SmokeTestAppender(str(directory))
    if operation == "prune":
        return appender.prune("demo", "sample")
    return appender.append(workflow(), dry_run=operation == "dry-run")


@pytest.mark.parametrize("operation", ["append", "dry-run", "prune"])
@pytest.mark.parametrize("link", ["symlink", "hardlink"])
def test_lock_alias_cannot_touch_sentinel(runtime, tmp_path, operation, link):
    """Reject a planted sidecar before any referent or catalog mutation."""
    directory = tmp_path / "catalog"
    directory.mkdir()
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"preserve-me")
    lock = directory / "demo.yaml.lock"
    if link == "symlink":
        lock.symlink_to(sentinel)
    else:
        os.link(sentinel, lock)
    try:
        with pytest.raises(OSError):
            mutate(runtime, directory, operation)
    finally:
        assert sentinel.read_bytes() == b"preserve-me"
        assert not (directory / "demo.yaml").exists()


@pytest.mark.parametrize("kind", ["dangling", "fifo", "directory", "foreign-owner"])
def test_unsafe_lock_types_fail_without_writing(runtime, tmp_path, monkeypatch, kind):
    """Nonregular sidecars must fail before locking or blocking on FIFO I/O."""
    lock = tmp_path / "demo.yaml.lock"
    if kind == "dangling":
        lock.symlink_to(tmp_path / "missing")
    elif kind == "fifo":
        os.mkfifo(lock)
    elif kind == "directory":
        lock.mkdir()
    else:
        lock.write_text("existing")
        uid = os.geteuid()
        monkeypatch.setattr(runtime.cat.os, "geteuid", lambda: uid + 1)
    with pytest.raises(OSError):
        mutate(runtime, tmp_path, "append")
    assert not (tmp_path / "demo.yaml").exists()
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize("operation", ["append", "prune"])
def test_symlinked_root_is_rejected(runtime, tmp_path, operation):
    """Reject the selected output root itself even when its parent is trusted."""
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "catalog"
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        mutate(runtime, root, operation)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("app", ["../outside", "/absolute", "x/y", "..", "demo\n", ""])
def test_invalid_app_never_creates_files(runtime, tmp_path, app):
    """Storage validation also protects prune/list, not just workflow append."""
    appender = runtime.SmokeTestAppender(str(tmp_path / "missing"))
    bad = workflow()
    bad["app"] = app
    for operation in [
        lambda: appender.append(bad),
        lambda: appender.prune(app, "x"),
        lambda: appender.list_coverage(app),
    ]:
        with pytest.raises(ValueError):
            operation()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("kind", ["symlink", "fifo", "directory"])
def test_catalog_read_rejects_unsafe_leaf(runtime, tmp_path, kind):
    """No symlink/nonregular catalog read precedes a safe atomic write."""
    path = tmp_path / "demo.yaml"
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("preserve")
    if kind == "symlink":
        path.symlink_to(sentinel)
    elif kind == "fifo":
        os.mkfifo(path)
    else:
        path.mkdir()
    with pytest.raises(OSError):
        mutate(runtime, tmp_path, "append")
    assert sentinel.read_text() == "preserve"


@pytest.mark.parametrize("when", ["lock", "replace"])
def test_root_swap_cannot_redirect_transaction(runtime, tmp_path, monkeypatch, when):
    """Directory entry replacement never changes the pinned transaction destination."""
    root = tmp_path / "catalog"
    root.mkdir()
    moved = tmp_path / "moved"
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "demo.yaml"
    target.write_text("outside sentinel")

    def swap():
        root.rename(moved)
        root.symlink_to(outside, target_is_directory=True)

    if when == "lock":
        original = runtime.cat.fcntl.flock

        def flock(fd, operation):
            original(fd, operation)
            if operation == runtime.cat.fcntl.LOCK_EX:
                swap()

        monkeypatch.setattr(runtime.cat.fcntl, "flock", flock)
    else:
        original = runtime.cat.os.replace

        def replace(src, dst, **kwargs):
            swap()
            original(src, dst, **kwargs)

        monkeypatch.setattr(runtime.cat.os, "replace", replace)
    mutate(runtime, root, "append")
    assert target.read_text() == "outside sentinel"
    assert (moved / "demo.yaml").is_file()
    assert sorted(p.name for p in outside.iterdir()) == ["demo.yaml"]
    assert not list(moved.glob("*.tmp"))


@pytest.mark.parametrize("when", ["lock", "write"])
def test_lock_replacement_fails_and_cleans_up(runtime, tmp_path, monkeypatch, when):
    """Detect replaced lock entries after waiting and before committing YAML."""
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("preserve")
    lock = tmp_path / "demo.yaml.lock"
    descriptors = []
    original = runtime.cat.fcntl.flock

    def swap():
        lock.unlink()
        lock.symlink_to(sentinel)

    def flock(fd, operation):
        original(fd, operation)
        if operation == runtime.cat.fcntl.LOCK_EX:
            descriptors.append(fd)
            if when == "lock":
                swap()

    monkeypatch.setattr(runtime.cat.fcntl, "flock", flock)
    if when == "write":
        dump = runtime.cat.dump_catalog

        def changed_dump(data):
            swap()
            return dump(data)

        monkeypatch.setattr(runtime.cat, "dump_catalog", changed_dump)
    with pytest.raises(OSError):
        mutate(runtime, tmp_path, "append")
    assert sentinel.read_text() == "preserve"
    assert not (tmp_path / "demo.yaml").exists()
    assert not list(tmp_path.glob("*.tmp"))
    for fd in descriptors:
        with pytest.raises(OSError):
            os.fstat(fd)


def test_regular_sidecar_and_hardlinked_catalog_preserve_other_inode(runtime, tmp_path):
    """Lock contents/inode persist; atomic replacement never truncates a hardlink."""
    lock = tmp_path / "demo.yaml.lock"
    lock.write_text("keep lock contents")
    inode = lock.stat().st_ino
    appender = runtime.SmokeTestAppender(str(tmp_path))
    appender.append(workflow("first"))
    sentinel = tmp_path / "catalog-copy"
    os.link(tmp_path / "demo.yaml", sentinel)
    before = sentinel.read_bytes()
    appender.append(workflow("second"))
    assert appender.prune("demo", "first")
    assert sentinel.read_bytes() == before
    assert [t["id"] for t in appender.list_coverage("demo")] == ["second"]
    assert lock.read_text() == "keep lock contents"
    assert lock.stat().st_ino == inode


@pytest.mark.parametrize("kind", ["absolute", "relative", "nested", "parent-alias"])
def test_legitimate_root_forms(runtime, tmp_path, monkeypatch, kind):
    """Keep explicit roots and trusted parent aliases, including macOS-style /tmp."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "catalog"
    if kind == "relative":
        root = Path("catalog")
    elif kind == "nested":
        root = tmp_path / "missing" / "nested" / "catalog"
    elif kind == "parent-alias":
        parent = tmp_path / "actual"
        parent.mkdir()
        alias = tmp_path / "alias"
        alias.symlink_to(parent, target_is_directory=True)
        root = alias / "catalog"
    mutate(runtime, root, "append")
    assert mutate(runtime, root, "prune") is True
    assert (root / "demo.yaml").is_file()


def run_cli(runtime, root, operation, args, data=None):
    """Invoke either shipped CLI with isolated package resolution."""
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "smoke_orchestrator",
            operation,
            *args,
            "--catalog-dir",
            str(root),
        ],
        env={**os.environ, "PYTHONPATH": str(Path(runtime.__file__).parents[1])},
        input=json.dumps(workflow() if data is None else data),
        capture_output=True,
        text=True,
        timeout=5,
    )


@pytest.mark.parametrize("operation", ["append", "prune"])
def test_cli_rejects_unsafe_lock_without_traceback(runtime, tmp_path, operation):
    """Both entry points preserve their I/O error exit contract."""
    sentinel = tmp_path / "sentinel"
    sentinel.write_text("preserve")
    (tmp_path / "demo.yaml.lock").symlink_to(sentinel)
    args = ["--stdin"] if operation == "append" else ["--app", "demo", "--id", "sample"]
    result = run_cli(runtime, tmp_path, operation, args)
    assert result.returncode == 1
    assert "I/O error" in result.stderr
    assert "Traceback" not in result.stderr
    assert sentinel.read_text() == "preserve"


def test_multiprocess_writers_share_stable_lock(runtime, tmp_path):
    """Real flock serializes distinct process updates without losing entries."""
    code = (
        "import sys; from smoke_orchestrator.appender import SmokeTestAppender; "
        "SmokeTestAppender(sys.argv[1]).append("
        "{'app':'demo','id':sys.argv[2],'tier':'Lite','steps':"
        "[{'name':'health','type':'api','method':'GET','path':'/health'}]})"
    )
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path), f"test-{i}"],
            env={**os.environ, "PYTHONPATH": str(Path(runtime.__file__).parents[1])},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for i in range(12)
    ]
    try:
        for process in processes:
            out, err = process.communicate(timeout=10)
            assert process.returncode == 0, (out, err)
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
            process.wait()
    assert len(runtime.SmokeTestAppender(str(tmp_path)).list_coverage("demo")) == 12


def test_failed_write_cleans_temporary_and_releases_lock(
    runtime, tmp_path, monkeypatch
):
    """A failed durable write leaves no partial YAML and permits a later update."""

    def fail(_fd):
        raise OSError("synthetic fsync failure")

    with monkeypatch.context() as patch:
        patch.setattr(runtime.cat.os, "fsync", fail)
        with pytest.raises(OSError, match="synthetic"):
            mutate(runtime, tmp_path, "append")
    assert not (tmp_path / "demo.yaml").exists()
    assert not list(tmp_path.glob("*.tmp"))
    mutate(runtime, tmp_path, "append")
    assert len(runtime.SmokeTestAppender(str(tmp_path)).list_coverage("demo")) == 1


def test_different_apps_do_not_share_a_lock(runtime, tmp_path):
    """Holding one app lock does not block another app's ordinary update."""
    other = workflow()
    other["app"] = "other"
    with runtime.cat.file_lock(tmp_path / "demo.yaml"):
        result = run_cli(runtime, tmp_path, "append", ["--stdin"], other)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "other.yaml").is_file()


@pytest.mark.parametrize("operation", ["append", "prune", "list"])
def test_parent_loop_keeps_cli_io_error_contract(runtime, tmp_path, operation):
    """Pathlib symlink-loop errors must not escape as CLI tracebacks."""
    loop = tmp_path / "loop"
    loop.symlink_to(loop)
    args = {
        "append": ["--stdin"],
        "prune": ["--app", "demo", "--id", "sample"],
        "list": ["--app", "demo"],
    }[operation]
    result = run_cli(runtime, loop / "catalog", operation, args)
    assert result.returncode == 1
    assert "I/O error" in result.stderr
    assert "Traceback" not in result.stderr
