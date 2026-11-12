"""Run isolated behavior scenarios for the deployed Python 3.9 hook floor."""

import json
import os
import shutil
import site
import subprocess
import sys
import tempfile
from pathlib import Path

from hook_compat_registration import (
    PLUGIN_CASES,
    PYTHON_CASES,
    ROOT,
    SCRIPTS,
    command_entry,
)


def _record_result(label, command, result):
    print(
        json.dumps(
            {
                "case": label,
                "command": command,
                "exit_status": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            },
            sort_keys=True,
        )
    )


def _failure(label, command, result):
    return (
        f"{label}: command={command!r} exit={result.returncode} "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def run_case(command, payload, env, home, stdout, stderr, label):
    result = subprocess.run(
        command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=home,
        check=False,
    )
    stdout_matches = stdout in result.stdout if stdout else result.stdout == ""
    stderr_matches = stderr in result.stderr if stderr else result.stderr == ""
    if (
        result.returncode != 0
        or not stdout_matches
        or not stderr_matches
        or "Traceback" in result.stderr
    ):
        raise AssertionError(_failure(label, command, result))
    _record_result(label, command, result)


def run_scenarios():
    with tempfile.TemporaryDirectory(prefix="manifest-hook-py39-") as temp:
        home = Path(temp)
        _prepare_fixture(home)
        env = _isolated_env(home)
        _run_managed_delegate(env, home)
        _run_shell_helper_scenarios(env, home)
        _run_python_hook_scenarios(env, home)
        run_plugin_cases(env, home)


def _prepare_fixture(home):
    shared = home / ".claude" / "scripts"
    shared.mkdir(parents=True)
    (shared / "manifest_model_policy").symlink_to(
        SCRIPTS / "manifest_model_policy", target_is_directory=True
    )
    sessions = home / "sessions" / "project"
    sessions.mkdir(parents=True)
    (sessions / "fixture.jsonl").write_text(
        json.dumps({"cwd": "/tmp/py39-victim"}) + "\n"
    )
    (home / "constitution_input.py").write_text("value = 1\n")
    (home / "docker-compose.yml").write_text(
        "services:\n  app:\n    image: nginx:1.27\n    environment:\n      DB_PASSWORD: plaintext\n"
    )


def _isolated_env(home):
    return {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / "xdg"),
        "XDG_STATE_HOME": str(home / "xdg-state"),
        "MANIFEST_STATE_ROOT": str(home / "state"),
        "MANIFEST_DELEGATIONS_DIR": str(home / "delegations"),
        "CLAUDE_SESSIONS_DIR": str(home / "sessions"),
        "CONSTITUTION_STATE_DIR": str(home / "constitution-state"),
        "GUIDANCE_STATE_DIR": str(home / "guidance-state"),
        "MANIFEST_COMPACTION_REMINDER_THRESHOLD": "1",
        "BLOCK_CWD_DELETE_WINDOW_MIN": "720",
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_COUNT": "0",
    }


def _run_managed_delegate(env, home):
    managed_python = next(
        (
            shutil.which(f"python3.{minor}")
            for minor in range(14, 10, -1)
            if shutil.which(f"python3.{minor}")
        ),
        None,
    )
    if managed_python is None:
        raise RuntimeError(
            "CPython >=3.11 is required to provision the managed delegate runtime"
        )
    venv = home / ".claude" / ".venv"
    subprocess.run(
        [managed_python, "-m", "venv", str(venv)], check=True, cwd=ROOT, env=env
    )
    subprocess.run(
        [
            str(venv / "bin/python"),
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            str(SCRIPTS / "manifest_model_policy"),
        ],
        check=True,
        cwd=ROOT,
        env=env,
    )
    config = home / ".claude" / "config"
    config.mkdir(parents=True)
    (config / "delegation.json").write_text('{"review_gate":{"enabled":true}}\n')
    transcript = home / "stop-transcript.jsonl"
    transcript.write_text('{"type":"user","message":{"content":"review"}}\n')
    root = ROOT / "plugins/manifest-delegate"
    run_case(
        ["sh", str(root / "scripts/stop_gate_hook.sh")],
        {"hook_event_name": "Stop", "transcript_path": str(transcript)},
        dict(env, CLAUDE_PLUGIN_ROOT=str(root)),
        home,
        '"decision":"approve"',
        "",
        "manifest-delegate Stop shell/Python/delegate no-edit path",
    )


def _run_shell_helper_scenarios(env, home):
    _run_spec_and_lint(env, home)
    _run_docs_lint(env, home)
    _run_version_pin(env, home)


def _lint_env(env):
    return dict(env, PATH=str(Path(sys.executable).parent) + os.pathsep + env["PATH"])


def _run_spec_and_lint(env, home):
    lint_env = _lint_env(env)
    model = home / "model_policy.yml"
    model.write_text("model_tiers:\n  antigravity:\n    advanced: compat-model\n")
    spec_command = [
        "bash",
        "-c",
        'source "$1"; resolve_review_model; printf "\\n"; format_findings \'{"finding":"x"}\' json',
        "spec-review-hook-test",
        str(SCRIPTS / "spec_review.sh"),
    ]
    result = subprocess.run(
        spec_command,
        text=True,
        capture_output=True,
        env=dict(lint_env, SPEC_REVIEW_CLI="agy", SPEC_REVIEW_CONFIG=str(model)),
        cwd=home,
        check=False,
    )
    if (
        result.returncode
        or result.stdout != 'compat-model\n["{\\"finding\\":\\"x\\"}"]\n'
        or "Traceback" in result.stderr
    ):
        raise AssertionError(
            _failure("spec_review.sh Python helpers", spec_command, result)
        )
    _record_result("spec_review.sh model/YAML and JSON helpers", spec_command, result)
    payload = {
        "tool_name": "Write",
        "tool_input": {"file_path": str(home / "hook-input.json")},
    }
    (home / "hook-input.json").write_text('{"ok": true}\n')
    lint_command = ["bash", str(SCRIPTS / "lint_on_edit_hook.sh")]
    lint = subprocess.run(
        lint_command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=lint_env,
        cwd=home,
        check=False,
    )
    if lint.returncode or "Traceback" in lint.stderr:
        raise AssertionError(_failure("lint_on_edit_hook.sh", lint_command, lint))
    _record_result("lint_on_edit_hook.sh JSON/constitution path", lint_command, lint)


def _run_docs_lint(env, home):
    root = home / "markdown-repo"
    config = root / "configs/claude/config"
    config.mkdir(parents=True)
    (config / "doc_limits.yml").write_text(
        "defaults:\n  max_lines: 1\n  warn_at: 0.8\n"
    )
    markdown = root / "over-cap.md"
    markdown.write_text("# First\nSecond\n")
    subprocess.run(["git", "init", "-q", str(root)], check=True, env=env)
    payload = {"tool_name": "Edit", "tool_input": {"file_path": str(markdown)}}
    docs_command = ["bash", str(SCRIPTS / "lint_on_edit_hook.sh")]
    result = subprocess.run(
        docs_command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=_lint_env(env),
        cwd=home,
        check=False,
    )
    if (
        result.returncode
        or f"lint-on-edit: {markdown}:" not in result.stderr
        or "docs_lint.py:" not in result.stderr
        or "1 over cap" not in result.stderr
        or "Traceback" in result.stderr
        or result.stdout
    ):
        raise AssertionError(
            _failure(
                "lint_on_edit_hook.sh Markdown/docs-lint path", docs_command, result
            )
        )
    _record_result("lint_on_edit_hook.sh Markdown/docs_lint path", docs_command, result)


def _run_version_pin(env, home):
    requirements = home / "requirements.txt"
    requirements.write_text("requests==2.31.0 --hash=sha256:abc123\n")
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(requirements)}}
    script = ROOT / "plugins/manifest-ops/runtime/bin/version_pin_hook.sh"
    version_command = ["bash", str(script)]
    result = subprocess.run(
        version_command,
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=_lint_env(env),
        cwd=home,
        check=False,
    )
    if (
        result.returncode
        or "Traceback" in result.stderr
        or result.stdout
        or f"version-pin: {requirements}" not in result.stderr
        or "Summary: 1 files, 0 violations reported, 1 compliant, 0 bypassed, 0 unresolved"
        not in result.stderr
    ):
        raise AssertionError(_failure("version_pin_hook.sh", version_command, result))
    _record_result("version_pin_hook.sh payload extraction", version_command, result)


def _run_python_hook_scenarios(env, home):
    _run_guidance_paths(env, home)
    stop = ROOT / "plugins/manifest-delegate/scripts/stop_gate_hook.py"
    run_case(
        [sys.executable, str(stop)],
        {"stop_hook_active": True},
        env,
        home,
        '"decision": "approve"',
        "",
        "manifest-delegate Stop recursion guard",
    )
    for name, case in PYTHON_CASES.items():
        run_case(
            [sys.executable, str(SCRIPTS / name), *case.get("args", [])],
            case["payload"],
            env,
            home,
            case["stdout"],
            case["stderr"],
            name,
        )


def _run_guidance_paths(env, home):
    payload = {
        "session_id": "x",
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "cwd": "/tmp",
    }
    script = SCRIPTS / "guidance_hint.py"
    run_case(
        [sys.executable, str(script)],
        payload,
        env,
        home,
        "",
        "",
        "guidance_hint.py explicit CPython 3.9 silent ls payload",
    )
    pathbin = home / "path-python"
    pathbin.mkdir()
    (pathbin / "python3").symlink_to(sys.executable)
    shebang_env = dict(
        env,
        PATH=str(pathbin) + os.pathsep + env["PATH"],
        PYTHONPATH=os.pathsep.join(site.getsitepackages()),
    )
    probe = home / "python39_shebang_probe.py"
    probe.write_text(
        "#!/usr/bin/env python3\nimport platform, sys\nassert platform.python_implementation() == 'CPython', platform.python_implementation()\nassert sys.version_info[:2] == (3, 9), sys.version\n"
    )
    probe.chmod(0o755)
    run_case(
        [str(probe)],
        {},
        shebang_env,
        home,
        "",
        "",
        "CPython 3.9 shebang/PATH interpreter probe",
    )
    run_case(
        [str(script)],
        payload,
        shebang_env,
        home,
        "",
        "",
        "guidance_hint.py shebang/PATH silent ls payload",
    )


def run_plugin_cases(env, home):
    for case in PLUGIN_CASES:
        root = ROOT / "plugins" / case["plugin"]
        manifest = json.loads((root / case["manifest"]).read_text())
        found = command_entry(
            case["event"], manifest["hooks"][case["event"]], case["script"]
        )
        if found != (case["event"], case["matcher"]):
            raise AssertionError(
                f"plugin hook registration mismatch: {case['plugin']}/{case['script']} {found!r}"
            )
        payload = dict(case["payload"])
        if case["script"].endswith("session_continuity.py"):
            payload["hook_event_name"] = case["event"]
        run_case(
            [sys.executable, str(root / case["script"]), *case["args"]],
            payload,
            dict(env, CLAUDE_PLUGIN_ROOT=str(root)),
            home,
            case["stdout"],
            case["stderr"],
            f"{case['plugin']}/{case['script']}:{case['event']}",
        )
        verify_plugin_state(case, home)


def verify_plugin_state(case, home):
    if (
        case["plugin"] == "manifest-workspace"
        and case["script"].endswith("session_continuity.py")
        and case["event"] == "SessionStart"
        and case["payload"].get("source") == "compact"
    ):
        files = list((home / "xdg-state/manifest/session-continuity").glob("*.json"))
        if len(files) != 1:
            raise AssertionError(
                "compact SessionStart did not persist continuity state"
            )
        state = json.loads(files[0].read_text())
        if state.get("compaction_count") != 1:
            raise AssertionError(
                "compact SessionStart did not increment compaction count: "
                + repr(state)
            )
    if case["plugin"] == "manifest-delegate" and case["event"] == "SessionStart":
        captured = home / ".manifest/delegate/sessions.json"
        if not captured.is_file() or "py39" not in captured.read_text():
            raise AssertionError(
                "manifest-delegate SessionStart did not capture its session"
            )
