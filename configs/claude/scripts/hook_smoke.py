#!/usr/bin/env python3
"""Verify the deployed fail-closed Stop hook without calling a real provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Mapping, Sequence

SCHEMA_VERSION = 1
MAX_TOTAL_SECONDS = 30.0
SERIALIZATION_RESERVE_SECONDS = 2.0
MAX_CAPTURE_BYTES = 64 * 1024
PLUGIN_KEY = "manifest-delegate@manifest"
EXPECTED_STOP_COMMAND = '/bin/sh "${CLAUDE_PLUGIN_ROOT}/scripts/stop_gate_hook.sh"'
ARTIFACTS = {
    "hooks.json": Path("hooks/hooks.json"),
    "stop_gate_hook.sh": Path("scripts/stop_gate_hook.sh"),
    "stop_gate_hook.py": Path("scripts/stop_gate_hook.py"),
    "delegate.py": Path("scripts/delegate.py"),
}


@dataclass(frozen=True)
class CommandResult:
    outcome: str
    returncode: int | None = None
    stdout: str = ""


Runner = Callable[
    [Sequence[str], str | None, Path, Mapping[str, str], float], CommandResult
]
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, ProcessLookupError, PermissionError, OSError):
        try:
            process.kill()
        except OSError:
            pass


def run_bounded(
    argv: Sequence[str],
    input_text: str | None,
    cwd: Path,
    environment: Mapping[str, str],
    deadline: float,
) -> CommandResult:
    """Run one argv-only command, reaping its process group at the deadline."""
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return CommandResult("timeout")
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                list(argv),
                cwd=str(cwd),
                env=dict(environment),
                stdin=subprocess.PIPE if input_text is not None else subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                start_new_session=True,
            )
        except (OSError, ValueError):
            return CommandResult("unavailable")
        try:
            process.communicate(
                input=input_text.encode("utf-8") if input_text is not None else None,
                timeout=max(0.01, remaining),
            )
        except subprocess.TimeoutExpired:
            _kill_process_group(process)
            try:
                process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                _kill_process_group(process)
            return CommandResult("timeout")

        stdout_file.seek(0)
        captured = stdout_file.read(MAX_CAPTURE_BYTES + 1)
        if len(captured) > MAX_CAPTURE_BYTES:
            return CommandResult("unparseable", process.returncode)
        return CommandResult(
            "complete",
            process.returncode,
            captured.decode("utf-8", errors="replace"),
        )


def resolve_plugin_root(home: Path, explicit: Path | None) -> Path | None:
    """Resolve only the exact plugin installation Claude records as active."""
    if explicit is not None:
        candidate = explicit.expanduser().resolve()
        return candidate if candidate.is_dir() else None
    index = home / ".claude/plugins/installed_plugins.json"
    try:
        document = json.loads(index.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(document, dict):
        return None
    entries = (document.get("plugins") or {}).get(PLUGIN_KEY)
    if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
        return None
    install_path = entries[0].get("installPath")
    if not isinstance(install_path, str) or not install_path:
        return None
    candidate = Path(install_path).expanduser().resolve()
    return candidate if candidate.is_dir() else None


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _measure_artifacts(plugin_root: Path) -> tuple[dict[str, str], str | None]:
    hashes: dict[str, str] = {}
    try:
        for name, relative in ARTIFACTS.items():
            path = plugin_root / relative
            if not path.is_file():
                return {}, "plugin_unavailable"
            hashes[name] = _sha256(path)
        launcher = plugin_root / ARTIFACTS["stop_gate_hook.sh"]
        if not os.access(launcher, os.R_OK | os.X_OK):
            return {}, "plugin_unavailable"
    except OSError:
        return {}, "plugin_unavailable"
    return hashes, None


def _valid_stop_registration(plugin_root: Path) -> bool:
    try:
        document = json.loads((plugin_root / ARTIFACTS["hooks.json"]).read_text())
        stop = document["hooks"]["Stop"]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    if not isinstance(stop, list):
        return False
    hooks = [
        hook
        for matcher in stop
        if isinstance(matcher, dict)
        for hook in matcher.get("hooks", [])
        if isinstance(hook, dict)
    ]
    return hooks == [
        {
            "type": "command",
            "command": EXPECTED_STOP_COMMAND,
            "timeout": 900,
        }
    ]


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


def _write_json(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")


def _write_smoke_fixture(root: Path, runtime_python: Path) -> dict[str, Path]:
    fixture = root / "fixture"
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

    backend = fixture / "stub_backend.py"
    backend.write_text(
        """#!/usr/bin/env python3
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
""",
        encoding="utf-8",
    )
    backend.chmod(0o700)
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


def _base_report(
    observed_at: datetime,
    hashes: Mapping[str, str],
    checks: Sequence[Mapping[str, str]],
    findings: Sequence[str],
) -> dict[str, object]:
    clean_findings = sorted(set(findings))
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": _timestamp(observed_at),
        "status": "degraded" if clean_findings else "ok",
        "hashes": dict(sorted(hashes.items())),
        "checks": [dict(item) for item in checks],
        "findings": clean_findings,
    }


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


def collect_smoke(
    *,
    home: Path,
    plugin_root: Path | None,
    environment: Mapping[str, str],
    deadline: float,
    runner: Runner = run_bounded,
    clock: Clock = utc_now,
) -> dict[str, object]:
    findings: list[str] = []
    checks: list[dict[str, str]] = []
    resolved_plugin = resolve_plugin_root(home, plugin_root)
    if resolved_plugin is None:
        return _base_report(clock(), {}, checks, ["plugin_unavailable"])

    hashes, artifact_error = _measure_artifacts(resolved_plugin)
    if artifact_error:
        findings.append(artifact_error)
    if not _valid_stop_registration(resolved_plugin):
        findings.append("hook_registration_invalid")
    runtime_python = home / ".claude/.venv/bin/python"
    if not runtime_python.is_file() or not os.access(runtime_python, os.X_OK):
        findings.append("runtime_unavailable")
    if findings:
        return _base_report(clock(), hashes, checks, findings)

    with tempfile.TemporaryDirectory(prefix="manifest-hook-smoke-") as temporary:
        root = Path(temporary)
        fixture = _write_smoke_fixture(root, runtime_python)
        child_environment = _smoke_environment(
            environment, home, resolved_plugin, fixture
        )
        repository = _prepare_git_repository(root, child_environment, deadline, runner)
        if repository is None:
            reason = "timeout" if time.monotonic() >= deadline else "git_unavailable"
            return _base_report(clock(), hashes, checks, [reason])

        launcher = resolved_plugin / ARTIFACTS["stop_gate_hook.sh"]
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
        for name, mode, payload in observations:
            if mode is not None:
                _write_json(
                    fixture["control"],
                    {"mode": mode, "spawn_count": str(fixture["spawn_count"])},
                )
            before = _spawn_count(fixture["spawn_count"])
            result, decision = _run_hook(
                launcher,
                payload,
                repository,
                child_environment,
                deadline,
                runner,
            )
            ok = _expected_observation(
                name, decision, before, _spawn_count(fixture["spawn_count"])
            )
            reason = "verified" if ok else _reason_from_result(result, decision)
            checks.append(_check(name, ok, reason))
            if not ok:
                findings.append(reason)

    return _base_report(clock(), hashes, checks, findings)


def _atomic_write(path: Path, document: Mapping[str, object]) -> bool:
    temporary_name: str | None = None
    try:
        path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
        os.chmod(path, 0o600)
        return True
    except OSError:
        return False
    finally:
        if temporary_name is not None:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass


def _positive_capped_timeout(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a number") from error
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return min(parsed, MAX_TOTAL_SECONDS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit sanitized JSON")
    parser.add_argument("--state-dir", type=Path)
    parser.add_argument("--plugin-root", type=Path)
    parser.add_argument(
        "--timeout-seconds",
        type=_positive_capped_timeout,
        default=MAX_TOTAL_SECONDS,
    )
    return parser


def _render_text(report: Mapping[str, object]) -> str:
    if report.get("status") == "ok":
        return "Hook smoke: ok"
    findings = report.get("findings")
    reason = ",".join(str(item) for item in findings[:3]) if isinstance(findings, list) else "unavailable"
    return f"Hook smoke: degraded ({reason[:120]})"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    environment = dict(os.environ)
    home = Path(environment.get("HOME") or Path.home()).expanduser()
    state_home = Path(
        environment.get("XDG_STATE_HOME") or home / ".local/state"
    ).expanduser()
    state_dir = (args.state_dir or state_home / "manifest/health").expanduser()

    started = time.monotonic()
    total_deadline = started + args.timeout_seconds
    reserve = min(
        SERIALIZATION_RESERVE_SECONDS,
        max(0.1, args.timeout_seconds * 0.1),
    )
    observation_deadline = total_deadline - reserve
    report = collect_smoke(
        home=home,
        plugin_root=args.plugin_root,
        environment=environment,
        deadline=observation_deadline,
    )
    receipt = state_dir / "hooks.json"
    if not _atomic_write(receipt, report):
        findings = list(report.get("findings") or [])
        findings.append("receipt_unwritable")
        report = {
            **report,
            "status": "degraded",
            "findings": sorted(set(findings)),
        }
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
