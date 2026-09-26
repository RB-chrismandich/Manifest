"""Shared fixtures for the health installer and report isolation tests."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

PACKAGE_VERSIONS = {"PyYAML": "6.0.3", "jsonschema": "4.26.0"}

REPORT_TIME = "2026-09-20T12:00:00Z"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def workspace_bundle() -> Path:
    return repo_root() / "plugins" / "manifest-workspace"


def isolated_env(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    state = tmp_path / "state"
    data = tmp_path / "data"
    config = tmp_path / "config"
    for path in (home, state, data, config):
        path.mkdir(parents=True)
    return {
        **os.environ,
        "HOME": str(home),
        "XDG_STATE_HOME": str(state),
        "XDG_DATA_HOME": str(data),
        "XDG_CONFIG_HOME": str(config),
        "UV_NO_NETWORK": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def run_script(
    script: Path, *args: str, env: dict[str, str], cwd: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(script), *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def load_runtime_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def file_row(path: Path) -> dict[str, str]:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "source": str(path),
        "destination": str(path),
        "source_sha256": digest,
        "destination_sha256": digest,
    }


def _write_contract_source(source_root: Path) -> None:
    contract_root = source_root / "plugins/manifest-workspace"
    contract_root.mkdir(parents=True)
    (contract_root / "manifest-capabilities.yml").write_text(
        """schema_version: 1
bundle:
  name: manifest-workspace
  version: 1.0.0
components:
  skills:
    root: skills
    include: ["*/SKILL.md"]
  agents: []
  hooks: []
  runtime: []
  guidance: []
capabilities:
  mcp:
    required: []
    default: [context7]
    optional: []
  executables:
    required: [python3]
    default: []
    optional: []
compatibility:
  claude: {mode: native}
  codex: {mode: native}
  gemini: {mode: generated}
  cursor: {mode: generated}
  antigravity: {mode: imported}
  devin: {mode: native}
""",
        encoding="utf-8",
    )
    contract_code = source_root / "src/manifest_agent/contracts.py"
    contract_code.parent.mkdir(parents=True)
    contract_code.write_text(
        "DOMAIN_BUNDLES = ('manifest-workspace',)\nADDON_BUNDLES = ()\n",
        encoding="utf-8",
    )


def _write_receipt(env: dict[str, str], now: datetime) -> Path:
    receipt = Path(env["XDG_STATE_HOME"]) / "manifest/installation.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "coordinator_version": "1.0.0",
                "release_version": "1.0.0",
                "source_commit": "a" * 40,
                "source_dirty": False,
                "archive_sha256": "b" * 64,
                "bundle_checksums": {"manifest-workspace": "c" * 64},
                "selected_optional": [],
                "harnesses": {
                    "claude": {
                        "harness": "claude",
                        "adapter_version": "1",
                        "native_version": "2.1.0",
                        "plugin_ids": ["manifest-workspace"],
                        "owned_entries": [],
                        "capabilities": {
                            "manifest-workspace:mcp:context7": "verified",
                            "manifest-workspace:executable:python3": "verified",
                        },
                        "verified": True,
                        "errors": [],
                    }
                },
                "migration_backup": None,
            }
        ),
        encoding="utf-8",
    )
    timestamp = now.timestamp()
    os.utime(receipt, (timestamp, timestamp))
    return receipt


def _write_pin_lock(agent_root: Path) -> None:
    owned = agent_root / "ui-expert.md"
    owned.parent.mkdir(parents=True)
    owned.write_text("owned\n", encoding="utf-8")
    pins = agent_root / "ui-workflow/dependencies.lock.json"
    pins.parent.mkdir(parents=True)
    pins.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "omp_version": "18.2.6",
                "python_version": platform.python_version(),
                "python_packages": PACKAGE_VERSIONS,
                "owned_files": {
                    "ui-expert.md": hashlib.sha256(owned.read_bytes()).hexdigest()
                },
            }
        ),
        encoding="utf-8",
    )


def _runtime_file_rows(runtime_root: Path) -> dict[str, dict[str, str]]:
    file_rows: dict[str, dict[str, str]] = {}
    for name in (
        "health_report.py",
        "health_report_collect.py",
        "health_report_common.py",
        "health_report_inspect.py",
        "health_report_sanitize.py",
        "mcp_health.py",
        "mcp_health_expectations.py",
        "mcp_health_report.py",
        "mcp_health_runtime.py",
        "health_install_files.py",
        "health_install_reconcile.py",
        "env_check.py",
        "hook_smoke.py",
        "hook_smoke_support.py",
    ):
        path = runtime_root / name
        path.write_text(f"# {name}\n", encoding="utf-8")
        file_rows[name] = file_row(path)
    return file_rows


def _write_health_installation(
    env: dict[str, str],
    tmp_path: Path,
    source_root: Path,
    runtime_root: Path,
    agent_root: Path,
    now: datetime,
) -> None:
    extension = agent_root / "extensions/manifest-health.ts"
    extension.parent.mkdir(parents=True)
    extension.write_text("extension\n", encoding="utf-8")
    wrapper = Path(env["HOME"]) / ".claude/scripts/mcp_health_check.sh"
    wrapper.parent.mkdir(parents=True)
    wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
    health_state = Path(env["XDG_STATE_HOME"]) / "manifest/health"
    health_state.mkdir(parents=True)
    (health_state / "installation.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "installed_at": now.isoformat().replace("+00:00", "Z"),
                "source_root": str(source_root),
                "executables": {
                    "python": str(Path(sys.executable).resolve()),
                    "omp": str(tmp_path / "bin/omp"),
                    "claude": str(tmp_path / "bin/claude"),
                    "coordinator": str(tmp_path / "bin/manifest"),
                },
                "files": _runtime_file_rows(runtime_root),
                "omp_extension": file_row(extension),
                "claude_wrapper": file_row(wrapper),
                "hook_hashes": {
                    "hooks.json": "a" * 64,
                    "stop_gate_hook.sh": "b" * 64,
                },
            }
        ),
        encoding="utf-8",
    )


def write_report_fixture(
    tmp_path: Path, now: datetime
) -> tuple[dict[str, str], Path, Path]:
    env = isolated_env(tmp_path)
    agent_root = tmp_path / "omp-agent"
    env["OMP_AGENT_DIR"] = str(agent_root)
    source_root = tmp_path / "report-source"
    _write_contract_source(source_root)
    receipt = _write_receipt(env, now)
    _write_pin_lock(agent_root)
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    _write_health_installation(
        env, tmp_path, source_root, runtime_root, agent_root, now
    )
    return env, runtime_root, receipt


class HealthyReportRunner:
    def __init__(self, module) -> None:
        self.module = module

    def _reconcile_result(self):
        return self.module.CommandResult(
            "complete",
            0,
            json.dumps(
                {
                    "operation": "reconcile",
                    "state": "READY",
                    "harnesses": {"claude": healthy_harness_record()},
                    "notes": [],
                    "errors": [],
                }
            ),
        )

    def _mcp_result(self, command: list[str]):
        harness = command[command.index("--harness") + 1]
        return self.module.CommandResult(
            "complete",
            0,
            json.dumps(
                {
                    "schema_version": 1,
                    "observed_at": REPORT_TIME,
                    "harness": harness,
                    "status": "ok",
                    "servers": [
                        {
                            "name": "context7",
                            "status": "healthy",
                            "reason_code": "connected",
                        }
                    ],
                }
            ),
        )

    def _hook_smoke_result(self):
        return self.module.CommandResult(
            "complete",
            0,
            json.dumps(
                {
                    "schema_version": 1,
                    "observed_at": REPORT_TIME,
                    "status": "ok",
                    "hashes": {
                        "hooks.json": "a" * 64,
                        "stop_gate_hook.sh": "b" * 64,
                    },
                    "checks": [],
                    "findings": [],
                }
            ),
        )

    def __call__(
        self,
        argv: list[Any],
        timeout_seconds: float,
        environment: dict[str, str],
    ):
        del timeout_seconds, environment
        command = [str(item) for item in argv]
        if command[-1:] == ["--version"]:
            version = "18.2.6" if Path(command[0]).name == "omp" else "2.1.0"
            return self.module.CommandResult("complete", 0, version + "\n")
        if "reconcile" in command:
            return self._reconcile_result()
        if Path(command[1]).name == "mcp_health.py":
            return self._mcp_result(command)
        if Path(command[1]).name == "hook_smoke.py":
            return self._hook_smoke_result()
        raise AssertionError(f"unexpected health command kind: {Path(command[0]).name}")


def healthy_harness_record() -> dict[str, Any]:
    return {
        "state": "READY",
        "installed_plugin_ids": ["manifest-workspace"],
        "capabilities": {
            "manifest-workspace:mcp:context7": "verified",
            "manifest-workspace:executable:python3": "verified",
        },
        "errors": [],
        "warnings": [],
    }


def collect_report(
    module, env: dict[str, str], runtime_root: Path, now: datetime, runner
):
    return module.collect_report(
        harnesses=("claude", "omp"),
        environment=env,
        runtime_dir=runtime_root,
        clock=lambda: now,
        runner=runner,
        package_version=PACKAGE_VERSIONS.get,
    )


__all__ = [
    "PACKAGE_VERSIONS",
    "REPORT_TIME",
    "HealthyReportRunner",
    "collect_report",
    "file_row",
    "healthy_harness_record",
    "isolated_env",
    "load_runtime_module",
    "repo_root",
    "run_script",
    "workspace_bundle",
    "write_report_fixture",
]
