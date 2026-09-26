"""Fixture generation and per-hook collection helpers for hook_smoke.py."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

ARTIFACTS = {
    "hooks.json": Path("hooks/hooks.json"),
    "stop_gate_hook.sh": Path("scripts/stop_gate_hook.sh"),
    "stop_gate_hook.py": Path("scripts/stop_gate_hook.py"),
    "delegate.py": Path("scripts/delegate.py"),
}

_STUB_BACKEND = """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ['MANIFEST_HOOK_SMOKE_CONTROL'], encoding='utf-8') as handle:
    control = json.load(handle)
with open(control['spawn_count'], 'a', encoding='utf-8') as handle:
    handle.write('spawned\\n')
sys.stdin.buffer.read()
if control.get('mode') == 'clean':
    envelope = {
        'backend': 'hook-smoke', 'model': None, 'outcome': 'success',
        'attempted': 'offline hook smoke fixture', 'changes': [],
        'succeeded': [], 'failed': [], 'follow_ups': [], 'findings': [],
    }
    print('```json')
    print(json.dumps(envelope, separators=(',', ':')))
    print('```')
else:
    print('invalid review fixture')
"""


@dataclass(frozen=True)
class CommandResult:
    outcome: str
    returncode: int | None = None
    stdout: str = ""


Runner = Callable[
    [Sequence[str], str | None, Path, Mapping[str, str], float], CommandResult
]


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")


def _fixture_paths(fixture: Path) -> dict[str, Path]:
    paths = {
        "config": fixture / "config",
        "jobs": fixture / "jobs",
        "xdg_config": fixture / "xdg-config",
        "spawn_count": fixture / "spawn-count.txt",
        "control": fixture / "control.json",
        "registry": fixture / "backends.json",
        "transcript": fixture / "transcript.jsonl",
    }
    for name in ("config", "jobs", "xdg_config"):
        paths[name].mkdir(parents=True)
    return paths


def _write_stub_backend(fixture: Path) -> Path:
    backend = fixture / "stub_backend.py"
    backend.write_text(_STUB_BACKEND, encoding="utf-8")
    backend.chmod(0o700)
    return backend


def _write_backend_config(
    paths: Mapping[str, Path], runtime_python: Path, backend: Path
) -> None:
    entry = {
        "id": "hook-smoke",
        "aliases": [],
        "binary": str(runtime_python),
        "invoke": [str(runtime_python), str(backend)],
        "resume": None,
        "model_args": [],
        "default_tier": "auto",
        "session_id_capture": {"method": "none"},
        "input": {
            "transport": "stdin",
            "max_payload_bytes": 1048576,
            "max_context_bytes": 1048576,
        },
        "readiness": {},
        "sandbox": {"read_only_args": [], "write_args": []},
    }
    _write_json(paths["registry"], {"backends": [entry]})
    _write_json(
        paths["config"] / "delegation.json",
        {
            "default_backend": "hook-smoke",
            "review_gate": {
                "enabled": True,
                "backend": "hook-smoke",
                "budget_seconds": 5,
            },
            "backends": {"hook-smoke": {"enabled": True}},
        },
    )


def _write_transcript(paths: Mapping[str, Path]) -> None:
    entries = (
        {"type": "user", "message": {"role": "user", "content": "smoke"}},
        {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "Edit", "input": {}}],
            },
        },
    )
    paths["transcript"].write_text(
        "".join(json.dumps(item, separators=(",", ":")) + "\n" for item in entries),
        encoding="utf-8",
    )


def _write_smoke_fixture(root: Path, runtime_python: Path) -> dict[str, Path]:
    fixture = root / "fixture"
    paths = _fixture_paths(fixture)
    backend = _write_stub_backend(fixture)
    _write_backend_config(paths, runtime_python, backend)
    _write_transcript(paths)
    return paths


def _spawn_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8").splitlines())
    except OSError:
        return 0


def _decision(result: CommandResult) -> dict[str, str] | None:
    if result.outcome != "complete" or result.returncode != 0:
        return None
    try:
        document = json.loads(result.stdout)
    except ValueError:
        return None
    if (
        not isinstance(document, dict)
        or document.get("decision") not in {"approve", "block"}
        or not isinstance(document.get("reason"), str)
        or not document["reason"]
    ):
        return None
    return {"decision": document["decision"], "reason": document["reason"]}


def _reason_from_result(result: CommandResult, decision: dict[str, str] | None) -> str:
    if result.outcome == "timeout":
        return "timeout"
    if result.outcome in {"unavailable", "unparseable"}:
        return result.outcome
    if decision is not None:
        for reason in (
            "jq_unavailable",
            "interpreter_unavailable",
            "invalid_decision",
            "wrapper_failed",
        ):
            if f"({reason})" in decision["reason"]:
                return reason
    return "unexpected_decision"


def _run_hook(
    launcher: Path,
    payload: Mapping[str, object],
    repository: Path,
    environment: Mapping[str, str],
    deadline: float,
    runner: Runner,
) -> tuple[CommandResult, dict[str, str] | None]:
    result = runner(
        ("/bin/sh", str(launcher)),
        json.dumps(payload, separators=(",", ":")),
        repository,
        environment,
        deadline,
    )
    return result, _decision(result)


def _check(name: str, ok: bool, reason: str) -> dict[str, str]:
    return {"name": name, "status": "ok" if ok else "degraded", "reason_code": reason}


def _prepare_git_repository(
    root: Path, environment: Mapping[str, str], deadline: float, runner: Runner
) -> Path | None:
    if shutil.which("git", path=environment.get("PATH")) is None:
        return None
    repository = root / "repo"
    repository.mkdir()
    tracked = repository / "fixture.txt"
    tracked.write_text("before\n", encoding="utf-8")
    commands = (
        ("git", "init", "-q"),
        ("git", "config", "user.email", "hook-smoke@example.invalid"),
        ("git", "config", "user.name", "Manifest Hook Smoke"),
        ("git", "add", "fixture.txt"),
        ("git", "commit", "-qm", "hook smoke fixture"),
    )
    for command in commands:
        result = runner(command, None, repository, environment, deadline)
        if result.outcome != "complete" or result.returncode != 0:
            return None
    tracked.write_text("after\n", encoding="utf-8")
    return repository


def _smoke_environment(
    base: Mapping[str, str],
    home: Path,
    plugin_root: Path,
    fixture: Mapping[str, Path],
) -> dict[str, str]:
    child = dict(base)
    child.update(
        {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(fixture["xdg_config"]),
            "MANIFEST_CONFIG_DIR": str(fixture["config"]),
            "MANIFEST_DELEGATIONS_DIR": str(fixture["jobs"]),
            "MANIFEST_DELEGATE_REGISTRY_PATH": str(fixture["registry"]),
            "MANIFEST_HOOK_SMOKE_CONTROL": str(fixture["control"]),
            "CLAUDE_PLUGIN_ROOT": str(plugin_root),
            "PYTHONPATH": "",
            "PYTHONDONTWRITEBYTECODE": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
        }
    )
    for name in (
        "CLAUDECODE",
        "MANIFEST_DELEGATE_RUNTIME_REEXEC",
        "MANIFEST_RUNTIME_PYTHON",
    ):
        child.pop(name, None)
    return child


def _expected_observation(
    name: str,
    decision: Mapping[str, str] | None,
    before_spawns: int,
    after_spawns: int,
) -> bool:
    if name == "clean_review":
        return (
            decision == {"decision": "approve", "reason": "no findings"}
            and after_spawns == before_spawns + 1
        )
    if name == "invalid_review":
        return (
            decision is not None
            and decision["decision"] == "block"
            and "Review gate could not verify this turn" in decision["reason"]
            and after_spawns == before_spawns + 1
        )
    return (
        decision == {"decision": "approve", "reason": "stop-hook-active"}
        and after_spawns == before_spawns
    )


def _observe_hook(
    name: str,
    mode: str | None,
    payload: Mapping[str, object],
    launcher: Path,
    fixture: Mapping[str, Path],
    repository: Path,
    environment: Mapping[str, str],
    deadline: float,
    runner: Runner,
) -> dict[str, str]:
    if mode is not None:
        _write_json(
            fixture["control"],
            {"mode": mode, "spawn_count": str(fixture["spawn_count"])},
        )
    before = _spawn_count(fixture["spawn_count"])
    result, decision = _run_hook(
        launcher, payload, repository, environment, deadline, runner
    )
    ok = _expected_observation(
        name, decision, before, _spawn_count(fixture["spawn_count"])
    )
    reason = "verified" if ok else _reason_from_result(result, decision)
    return _check(name, ok, reason)


def _run_observations(
    launcher: Path,
    fixture: Mapping[str, Path],
    repository: Path,
    environment: Mapping[str, str],
    deadline: float,
    runner: Runner,
) -> tuple[list[dict[str, str]], list[str]]:
    review_payload = {
        "hook_event_name": "Stop",
        "transcript_path": str(fixture["transcript"]),
    }
    observations = (
        ("clean_review", "clean", review_payload),
        ("invalid_review", "invalid", review_payload),
        (
            "recursion_guard",
            None,
            {"hook_event_name": "Stop", "stop_hook_active": True},
        ),
    )
    checks: list[dict[str, str]] = []
    findings: list[str] = []
    for name, mode, payload in observations:
        check = _observe_hook(
            name,
            mode,
            payload,
            launcher,
            fixture,
            repository,
            environment,
            deadline,
            runner,
        )
        checks.append(check)
        if check["status"] != "ok":
            findings.append(check["reason_code"])
    return checks, findings


def _collect_hook_checks(
    *,
    home: Path,
    plugin_root: Path,
    runtime_python: Path,
    environment: Mapping[str, str],
    deadline: float,
    runner: Runner,
) -> tuple[list[dict[str, str]], list[str]]:
    """Run the fixture-backed hook observations inside a temporary root."""
    with tempfile.TemporaryDirectory(prefix="manifest-hook-smoke-") as temporary:
        root = Path(temporary)
        fixture = _write_smoke_fixture(root, runtime_python)
        child_environment = _smoke_environment(environment, home, plugin_root, fixture)
        repository = _prepare_git_repository(root, child_environment, deadline, runner)
        if repository is None:
            reason = "timeout" if time.monotonic() >= deadline else "git_unavailable"
            return [], [reason]
        launcher = plugin_root / ARTIFACTS["stop_gate_hook.sh"]
        return _run_observations(
            launcher,
            fixture,
            repository,
            child_environment,
            deadline,
            runner,
        )
