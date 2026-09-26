#!/usr/bin/env python3
"""Verify the deployed fail-closed Stop hook without calling a real provider."""

from __future__ import annotations

import sys

# No __pycache__ beside the deployed scripts. The importing script — not the
# imported module — decides this, and an orphaned cache directory in a tree that
# apm and bootstrap own has previously caused them to decline it.
sys.dont_write_bytecode = True

import argparse  # noqa: E402
import hashlib  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import signal  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import time  # noqa: E402
from collections.abc import Callable, Mapping, Sequence  # noqa: E402
from contextlib import suppress  # noqa: E402
from datetime import UTC, datetime  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))

from hook_smoke_support import (  # noqa: E402
    ARTIFACTS,
    CommandResult,
    Runner,
    _check,
    _collect_hook_checks,
    _decision,
    _expected_observation,
    _prepare_git_repository,
    _reason_from_result,
    _run_hook,
    _smoke_environment,
    _spawn_count,
    _write_json,
    _write_smoke_fixture,
)

__all__ = [
    "ARTIFACTS",
    "Clock",
    "CommandResult",
    "Runner",
    "_check",
    "_collect_hook_checks",
    "_decision",
    "_expected_observation",
    "_prepare_git_repository",
    "_reason_from_result",
    "_run_hook",
    "_smoke_environment",
    "_spawn_count",
    "_write_json",
    "_write_smoke_fixture",
    "build_parser",
    "collect_smoke",
    "main",
    "resolve_plugin_root",
    "run_bounded",
    "utc_now",
]

SCHEMA_VERSION = 1
MAX_TOTAL_SECONDS = 30.0
SERIALIZATION_RESERVE_SECONDS = 2.0
MAX_CAPTURE_BYTES = 64 * 1024
PLUGIN_KEY = "manifest-delegate@manifest"
EXPECTED_STOP_COMMAND = '/bin/sh "${CLAUDE_PLUGIN_ROOT}/scripts/stop_gate_hook.sh"'

Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime) -> str:
    return (
        value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )


def _kill_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except (AttributeError, ProcessLookupError, PermissionError, OSError):
        with suppress(OSError):
            process.kill()


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
    with (
        tempfile.TemporaryFile() as stdout_file,
        tempfile.TemporaryFile() as stderr_file,
    ):
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

    checks, findings = _collect_hook_checks(
        home=home,
        plugin_root=resolved_plugin,
        runtime_python=runtime_python,
        environment=environment,
        deadline=deadline,
        runner=runner,
    )
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
            with suppress(OSError):
                os.unlink(temporary_name)


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
    reason = (
        ",".join(str(item) for item in findings[:3])
        if isinstance(findings, list)
        else "unavailable"
    )
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
