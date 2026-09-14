"""Remote jobs must not inherit local retry, sandbox, or process semantics."""

import importlib
import json
import subprocess

import pytest
from _delegate_inproc import delegate


@pytest.fixture
def remote():
    assert importlib.util.find_spec("manifest_delegate.remote_task"), (
        "remote task support missing"
    )
    return importlib.import_module("manifest_delegate.remote_task")


@pytest.fixture
def cli_adapter():
    assert importlib.util.find_spec("manifest_delegate.jules_cli"), (
        "Jules adapter missing"
    )
    return importlib.import_module("manifest_delegate.jules_cli")


def test_jules_declares_remote_scope():
    entry = delegate.resolve_backend(delegate.load_registry(), "jules")
    assert entry is not None
    assert entry["execution"]["kind"] == "remote_session"
    assert entry["execution"]["read_only"] is False


@pytest.mark.parametrize(
    "output", ["", "Error: did you forget to login?", "unknown output"]
)
def test_auth_requires_positive_repository_evidence(cli_adapter, output):
    assert not cli_adapter.parse_repositories(output)


def test_repository_probe_ignores_update_diagnostics(cli_adapter):
    assert cli_adapter.parse_repositories(
        "Self update failed, error: network unavailable\nexample/repository\n"
    ) == {"example/repository"}


def test_plain_auth_error_never_turns_arbitrary_log_path_into_repo(cli_adapter):
    assert cli_adapter.parse_repositories("Error: unavailable\ncache/file\n") == set()


@pytest.mark.parametrize(
    "status,want",
    [
        ("Completed", "completed"),
        ("Failed", "failed"),
        ("Awaiting User F", "remote_pending"),
        ("", None),
    ],
)
def test_session_status_requires_correct_row_and_column(cli_adapter, status, want):
    output = (
        " ID   Description   Repo   Last active   Status\n"
        " 999   Other task   example/repo   1 day ago   Completed\n"
        f" 123   Completed is only the title   example/repo   2h ago   {status}\n"
    )
    assert cli_adapter.parse_session_state(output, "123") == want
    assert cli_adapter.parse_session_state(output, "12") is None


def test_submission_needs_unique_session_link(cli_adapter):
    assert cli_adapter.parse_session_id("https://jules.google.com/session/123") == "123"
    assert cli_adapter.parse_session_id("Created task, no link") is None
    assert (
        cli_adapter.parse_session_id(
            "https://jules.google.com/session/123 https://jules.google.com/session/456"
        )
        is None
    )


def test_timeout_kills_the_entire_isolated_jules_process_group(
    cli_adapter, monkeypatch
):
    calls = []

    class Process:
        pid = 123

        def communicate(self, input=None, timeout=None):
            calls.append((input, timeout))
            if timeout is not None:
                raise subprocess.TimeoutExpired("jules", timeout)
            return None, None

    launched = {}

    def popen(*args, **kwargs):
        launched["args"] = args
        launched["kwargs"] = kwargs
        return Process()

    killed = []
    monkeypatch.setattr(cli_adapter.subprocess, "Popen", popen)
    monkeypatch.setattr(
        cli_adapter.os, "killpg", lambda pgid, sig: killed.append((pgid, sig))
    )
    with pytest.raises(subprocess.TimeoutExpired):
        cli_adapter.run(["jules", "remote", "list"], payload=b"request", timeout=1)
    assert calls == [(b"request", 1), (None, None)]
    assert killed == [(123, cli_adapter.signal.SIGKILL)]


def test_interruption_kills_the_isolated_jules_process_group(cli_adapter, monkeypatch):
    class Process:
        pid = 456

        def communicate(self, input=None, timeout=None):
            if timeout is not None:
                raise KeyboardInterrupt
            return None, None

    killed = []
    monkeypatch.setattr(
        cli_adapter.subprocess, "Popen", lambda *args, **kwargs: Process()
    )
    monkeypatch.setattr(
        cli_adapter.os, "killpg", lambda pgid, sig: killed.append((pgid, sig))
    )
    with pytest.raises(KeyboardInterrupt):
        cli_adapter.run(["jules", "remote", "list"])
    assert killed == [(456, cli_adapter.signal.SIGKILL)]


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MANIFEST_DELEGATIONS_DIR", str(tmp_path / "jobs"))
    return tmp_path


def test_unknown_submission_is_durable_and_never_retried(remote, isolated, monkeypatch):
    store = delegate.JobStore(root=str(isolated / "store"))
    calls = []

    def timeout(*args, **kwargs):
        calls.append(args)
        raise subprocess.TimeoutExpired("jules", 1)

    monkeypatch.setattr(remote.jules_cli, "run", timeout)
    record = remote.submit(store, "jules", "example/repo", b"implement task", 1)
    assert record["state"] == "remote_submission_unknown"
    assert len(calls) == 1
    assert store.reap_if_dead(record["job_id"])["state"] == "remote_submission_unknown"
    store._prune()
    assert store.read(record["job_id"])["state"] == "remote_submission_unknown"


def test_accepted_submission_is_pending_not_completed(
    remote, cli_adapter, isolated, monkeypatch
):
    store = delegate.JobStore(root=str(isolated / "store"))
    monkeypatch.setattr(
        remote.jules_cli,
        "run",
        lambda *a, **k: cli_adapter.CommandResult(
            0, "Created https://jules.google.com/session/123", ""
        ),
    )
    record = remote.submit(store, "jules", "example/repo", b"implement task", 10)
    assert record["state"] == "remote_pending"
    assert record["remote"]["session_id"] == "123"
    assert "envelope" not in record


@pytest.mark.parametrize(
    "extra",
    [
        [],
        ["--write"],
        ["--remote-write", "--resume", "123"],
        ["--remote-write", "--model-chain", "auto,high"],
    ],
)
def test_invalid_remote_scope_never_submits(remote, isolated, monkeypatch, extra):
    args = delegate.cli.build_parser().parse_args(
        [
            "task",
            "--backend",
            "jules",
            "--repo",
            "example/repo",
            "--remote-base",
            "provider-selected",
            *extra,
            "task",
        ]
    )
    entry = delegate.resolve_backend(delegate.load_registry(), "jules")
    assert remote.validate_request(args, entry, {}) is not None


def test_remote_cancel_does_not_claim_cloud_cancellation(
    remote, isolated, capsys, monkeypatch
):
    monkeypatch.setenv(delegate.constants.DELEGATIONS_DIR_ENV, str(isolated / "store"))
    store = delegate.JobStore()
    record = store.create(
        "jules", {"execution_kind": "remote_session", "state": "remote_pending"}
    )
    args = delegate.cli.build_parser().parse_args(
        ["cancel", record["job_id"], "--json"]
    )
    assert delegate.jobs_cli.cmd_cancel(args) == 2
    assert store.read(record["job_id"])["state"] == "remote_pending"
    assert "remote" in capsys.readouterr().err


def test_review_rejects_remote_before_diff_or_auth(remote, isolated, capsys):
    args = delegate.cli.build_parser().parse_args(["review", "--backend", "jules"])
    assert delegate.review.cmd_review(args, delegate.load_registry(), {}, set()) == 2
    assert "read-only" in capsys.readouterr().err


def test_registry_rejects_incoherent_remote_capabilities(remote, tmp_path):
    data = {"backends": [delegate.resolve_backend(delegate.load_registry(), "jules")]}
    data["backends"][0]["execution"]["read_only"] = True
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(data))
    with pytest.raises(delegate.RegistryError, match="remote"):
        delegate.load_registry(str(path))
