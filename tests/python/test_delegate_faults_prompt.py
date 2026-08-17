"""SC-004 fault-injection matrix for the delegate dispatcher.

Every dispatcher failure path must be explicit (states what happened),
attributed (names the backend/limit/layer responsible), and actionable
(names what to check or do next). This file drives one test per fault in
the matrix via delegate.py's public functions only; delegate.py itself is
never modified or read in full (see module docstring conventions in
test_delegate_dispatcher.py, which this file mirrors).
"""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "plugins" / "manifest-delegate" / "scripts" / "delegate.py"


def _load_delegate():
    spec = importlib.util.spec_from_file_location("delegate_faults", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


delegate = _load_delegate()


def _valid_backend(id_="codex", aliases=None):
    return {
        "id": id_,
        "aliases": aliases or [],
        "display_name": id_.title(),
        "binary": id_,
        "invoke": [id_, "exec", "{prompt}"],
        "resume": None,
        "model_args": ["--model", "{model}"],
        "tier_source": id_,
        "default_tier": "auto",
        "session_id_capture": {"mode": "none"},
        "input": {
            "transport": "stdin",
            "max_payload_bytes": 1000000,
            "max_context_bytes": None,
        },
        "readiness": {
            "version_cmd": [id_, "--version"],
            "auth_probe_cmd": [id_, "whoami"],
            "install_fix": f"install {id_}",
            "login_fix": f"login {id_}",
        },
        "sandbox": {"read_only_args": ["--read-only"], "write_args": ["--write"]},
        "prompting_ref": f"skills/delegate/references/{id_}.md",
        "services_key": id_,
    }


class _TaskArgs:
    backend = None
    background = False
    wait = True
    write = False
    model = None
    budget = None
    resume = None
    resume_last = False
    fresh = False
    second_opinion = False
    of = None
    task_file = None
    prompt_file = None
    prompt = "do the thing"
    json = True
    recovery_id = None


def _assert_explicit_attributed_actionable(
    message, backend_id=None, actionable_markers=()
):
    """Shared SC-004 assertion: message is non-empty/specific, names the
    backend/limit/layer responsible, and points at what to check/do next.
    """
    assert message and message.strip(), "failure message must not be empty"
    if backend_id is not None:
        assert backend_id in message, (
            f"message must attribute the failure to backend {backend_id!r}: {message!r}"
        )
    assert actionable_markers, "must supply at least one actionable marker to check for"
    assert any(marker in message for marker in actionable_markers), (
        f"message must be actionable (contain one of {actionable_markers!r}): {message!r}"
    )


def _make_args(tmp_path, monkeypatch, backend="codex"):
    monkeypatch.setenv(delegate.DELEGATIONS_DIR_ENV, str(tmp_path / "delegations"))
    monkeypatch.chdir(tmp_path)
    args = _TaskArgs()
    args.backend = backend
    return args


# ---------------------------------------------------------------------------
# 1. unknown backend
# ---------------------------------------------------------------------------


class TestPromptFileFault:
    """K4: a bad --prompt-file must exit 2 with an explicit message, never
    traceback (D3: never crash on bad input)."""

    def test_nonexistent_prompt_file_exits_2_with_message(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = None
        args.prompt_file = str(tmp_path / "does-not-exist.txt")
        rc = delegate.cmd_task(args, [_valid_backend("codex")], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "delegate: cannot read --prompt-file" in err
        assert args.prompt_file in err

    def test_directory_as_prompt_file_exits_2_with_message(
        self, tmp_path, monkeypatch, capsys
    ):
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = None
        args.prompt_file = str(tmp_path)
        rc = delegate.cmd_task(args, [_valid_backend("codex")], {}, set())
        err = capsys.readouterr().err
        assert rc == 2
        assert "delegate: cannot read --prompt-file" in err
        assert "directory" in err

    def test_oversized_prompt_file_is_bounded_at_acquisition(
        self, tmp_path, monkeypatch, capsys
    ):
        prompt = tmp_path / "large.txt"
        with prompt.open("wb") as stream:
            stream.seek(1024 * 1024)
            stream.write(b"xx")
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = None
        args.prompt_file = str(prompt)

        rc = delegate.cmd_task(args, [_valid_backend("codex")], {}, set())

        assert rc == 2
        assert "1 MiB task limit" in capsys.readouterr().err

    def test_symlink_prompt_file_is_rejected(self, tmp_path, monkeypatch, capsys):
        target = tmp_path / "target.txt"
        target.write_text("task")
        prompt = tmp_path / "prompt.txt"
        prompt.symlink_to(target)
        args = _make_args(tmp_path, monkeypatch)
        args.prompt = None
        args.prompt_file = str(prompt)

        rc = delegate.cmd_task(args, [_valid_backend("codex")], {}, set())

        assert rc == 2
        assert "safe regular file" in capsys.readouterr().err
