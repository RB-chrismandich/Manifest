"""Remote observation, artifact handling, and non-mutating capability boundaries."""

import importlib
import subprocess
from pathlib import Path

import pytest
from _delegate_inproc import delegate

jobs = importlib.import_module("manifest_delegate.remote_jobs")
jules = importlib.import_module("manifest_delegate.jules_cli")
remote = importlib.import_module("manifest_delegate.remote_task")


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(delegate.constants.DELEGATIONS_DIR_ENV, str(tmp_path / "jobs"))
    return delegate.JobStore()


def create(store, state="remote_pending"):
    return store.create(
        "jules",
        {
            "execution_kind": "remote_session",
            "state": state,
            "remote": {
                "driver": "jules_cli",
                "session_id": "123",
                "repository": "example/repo",
                "url": "https://jules.google.com/session/123",
            },
        },
    )


def test_missing_session_does_not_become_completed(store, monkeypatch):
    record = create(store)
    monkeypatch.setattr(jules, "run", lambda *a, **k: jules.CommandResult(0, "", ""))
    observed = jobs.refresh(store, record)
    assert observed["state"] == "remote_pending"
    assert "unavailable" in observed["status_error"]


def test_remote_pending_survives_local_reaping_and_retention(store, monkeypatch):
    record = create(store)
    monkeypatch.setattr(delegate.constants, "KEEP_LAST_N", 0)
    store._prune()
    assert store.reap_if_dead(record["job_id"])["state"] == "remote_pending"


def test_status_completion_does_not_invent_assistant_findings(store, monkeypatch):
    record = create(store)
    table = "ID   Description   Repo   Last active   Status\n123   Task   example/repo   1 day ago   Completed\n"
    monkeypatch.setattr(jules, "run", lambda *a, **k: jules.CommandResult(0, table, ""))
    observed = jobs.refresh(store, record)
    assert observed["state"] == "completed"
    assert "envelope" not in observed


def test_stale_status_observation_preserves_newer_record(store, monkeypatch):
    record = create(store)
    store.mutate(record["job_id"], lambda rec: dict(rec, state="completed"))
    monkeypatch.setattr(jules, "run", lambda *a, **k: jules.CommandResult(0, "", ""))
    assert jobs.refresh(store, record)["state"] == "completed"


def test_unknown_status_wait_exits_with_failure_instead_of_looping(store, monkeypatch):
    record = create(store)
    monkeypatch.setattr(
        jules, "run", lambda *a, **k: jules.CommandResult(0, "new format", "")
    )
    args = delegate.cli.build_parser().parse_args(
        ["status", record["job_id"], "--wait", "--timeout", "1"]
    )
    assert jobs.status(store, args, record) == 1


def test_pull_stores_patch_without_apply(store, monkeypatch):
    record = create(store, "completed")
    patch = "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"

    def run(argv, **kwargs):
        assert argv == ["jules", "remote", "pull", "--session", "123"]
        assert kwargs["cwd"] == store.job_dir(record["job_id"])
        return jules.CommandResult(0, patch, "")

    monkeypatch.setattr(jules, "run", run)
    args = delegate.cli.build_parser().parse_args(["pull", record["job_id"]])
    assert jobs.cmd_pull(args) == 0
    assert (
        Path(store.job_dir(record["job_id"])) / "changes.patch"
    ).read_text() == patch
    assert not Path("a.txt").exists()


@pytest.mark.parametrize(
    "text", ["Error: no patch", "", "No changes", "Self update failed\n"]
)
def test_pull_does_not_store_error_output_as_patch(store, monkeypatch, text):
    record = create(store, "completed")
    monkeypatch.setattr(jules, "run", lambda *a, **k: jules.CommandResult(0, text, ""))
    args = delegate.cli.build_parser().parse_args(["pull", record["job_id"]])
    assert jobs.cmd_pull(args) == 1
    assert not (Path(store.job_dir(record["job_id"])) / "changes.patch").exists()


def test_apply_uses_saved_patch_in_clean_matching_repo(store):
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/repo.git"],
        check=True,
    )
    Path("a.txt").write_text("old\n")
    # Keep the isolated job store out of git's clean-tree check.
    Path(".gitignore").write_text("jobs/\n")
    subprocess.run(["git", "add", "a.txt", ".gitignore"], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    record = create(store, "completed")
    path = Path(store.job_dir(record["job_id"])) / "changes.patch"
    path.write_text(
        "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"
    )
    args = delegate.cli.build_parser().parse_args(["apply", record["job_id"]])
    assert jobs.cmd_apply(args) == 0
    assert Path("a.txt").read_text() == "new\n"
    # A second apply cannot overwrite dirty user work.
    Path("a.txt").write_text("user edit\n")
    assert jobs.cmd_apply(args) == 1
    assert Path("a.txt").read_text() == "user edit\n"


def test_apply_accepts_case_and_url_form_mismatch_against_recorded_repo(store):
    """The recorded repository and the local `origin` remote must match up to
    GitHub's case-insensitivity and accepted URL forms (ssh://, git@, https),
    not by raw string equality."""
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "ssh://git@github.com/Example/Repo.git"],
        check=True,
    )
    Path("a.txt").write_text("old\n")
    Path(".gitignore").write_text("jobs/\n")
    subprocess.run(["git", "add", "a.txt", ".gitignore"], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    record = store.create(
        "jules",
        {
            "execution_kind": "remote_session",
            "state": "completed",
            "remote": {
                "driver": "jules_cli",
                "session_id": "123",
                "repository": "example/repo",
                "url": "https://jules.google.com/session/123",
            },
        },
    )
    path = Path(store.job_dir(record["job_id"])) / "changes.patch"
    path.write_text(
        "diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-old\n+new\n"
    )
    args = delegate.cli.build_parser().parse_args(["apply", record["job_id"]])
    assert jobs.cmd_apply(args) == 0
    assert Path("a.txt").read_text() == "new\n"


def test_apply_from_subdirectory_applies_root_level_patch(store, monkeypatch):
    subprocess.run(["git", "init", "-q"], check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/example/repo.git"],
        check=True,
    )
    Path("root.txt").write_text("old\n")
    Path(".gitignore").write_text("jobs/\n")
    subprocess.run(["git", "add", "root.txt", ".gitignore"], check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.hooksPath=/dev/null",
            "commit",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    root = Path.cwd()
    subdirectory = root / "nested"
    subdirectory.mkdir()
    monkeypatch.chdir(subdirectory)
    scoped_store = delegate.JobStore()
    record = create(scoped_store, "completed")
    path = Path(scoped_store.job_dir(record["job_id"])) / "changes.patch"
    path.write_text(
        "diff --git a/root.txt b/root.txt\n--- a/root.txt\n+++ b/root.txt\n@@ -1 +1 @@\n-old\n+new\n"
    )
    args = delegate.cli.build_parser().parse_args(["apply", record["job_id"]])
    assert jobs.cmd_apply(args) == 0
    assert (root / "root.txt").read_text() == "new\n"


def test_pull_resolves_remote_job_created_in_a_different_workspace(
    tmp_path, monkeypatch
):
    """A job submitted from one directory must still be pull/apply/status-able
    from another: remote sessions are not tied to the invoking cwd, unlike
    local subprocess jobs."""
    monkeypatch.setenv(delegate.constants.DELEGATIONS_DIR_ENV, str(tmp_path / "jobs"))
    origin_dir = tmp_path / "origin"
    origin_dir.mkdir()
    monkeypatch.chdir(origin_dir)
    origin_store = delegate.JobStore()
    record = create(origin_store, "completed")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(
        jules,
        "run",
        lambda *a, **k: jules.CommandResult(0, "diff --git a/x b/x\n", ""),
    )
    args = delegate.cli.build_parser().parse_args(["pull", record["job_id"]])
    assert jobs.cmd_pull(args) == 0


def test_status_resolves_remote_job_created_in_a_different_workspace(
    tmp_path, monkeypatch
):
    jobs_cli = importlib.import_module("manifest_delegate.jobs_cli")
    monkeypatch.setenv(delegate.constants.DELEGATIONS_DIR_ENV, str(tmp_path / "jobs"))
    origin_dir = tmp_path / "origin"
    origin_dir.mkdir()
    monkeypatch.chdir(origin_dir)
    origin_store = delegate.JobStore()
    record = create(origin_store, "remote_pending")

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    table = (
        "ID   Description   Repo   Last active   Status\n"
        "123   Task   example/repo   1 day ago   Completed\n"
    )
    monkeypatch.setattr(jules, "run", lambda *a, **k: jules.CommandResult(0, table, ""))
    args = delegate.cli.build_parser().parse_args(["status", record["job_id"]])
    assert jobs_cli.cmd_status(args) == 0


@pytest.mark.parametrize("command", ["pull", "apply"])
def test_remote_commands_require_a_job_id_when_jobs_exist(store, capsys, command):
    create(store, "completed")
    args = delegate.cli.build_parser().parse_args([command])
    assert getattr(jobs, f"cmd_{command}")(args) == 1
    assert "job id" in capsys.readouterr().err


def test_default_remote_backend_does_not_hijack_local_resume(store, monkeypatch):
    record = store.create("codex", {"state": "completed"})
    args = delegate.cli.build_parser().parse_args(
        ["task", "--resume", record["job_id"], "continue local work"]
    )
    called = {}

    def local(*args):
        called["local"] = args
        return 17

    monkeypatch.setattr(delegate.task, "_cmd_local_task", local)
    assert (
        delegate.task.cmd_task(
            args, delegate.load_registry(), {"default_backend": "jules"}, set()
        )
        == 17
    )
    assert called["local"]


def test_remote_resume_by_id_is_rejected_without_backend_arg(store, capsys):
    record = create(store)
    args = delegate.cli.build_parser().parse_args(
        ["task", "--resume", record["job_id"], "follow up"]
    )
    assert delegate.task.cmd_task(args, delegate.load_registry(), {}, set()) == 2
    assert "remote resume" in capsys.readouterr().err


def test_remote_gate_rejects_backend_without_spawning():
    entry, error = delegate.gate._gate_resolve_backend(
        {"backend": "jules"}, delegate.load_registry(), {}, set()
    )
    assert entry is None
    assert "read-only" in error


def test_disabled_nested_bootstrap_service_reaches_delegate(tmp_path):
    (tmp_path / "services.yml").write_text(
        "services:\n  jules:\n    enabled: false\n  codex:\n    enabled: true\n"
    )
    assert delegate.config.load_services_disabled(str(tmp_path)) == {"jules"}


def test_positive_auth_probe_never_returns_repository_names_as_identity(monkeypatch):
    entry = delegate.resolve_backend(delegate.load_registry(), "jules")
    monkeypatch.setattr(
        delegate.readiness,
        "_run_readiness_probe",
        lambda argv, **kwargs: (
            0,
            "Version: v0.1.42" if argv[-1] == "version" else "example/repo",
        ),
    )
    row = delegate.readiness.probe_backend_readiness(entry, {}, set())
    assert row["state"] == "ready"
    assert row["identity"] is None
