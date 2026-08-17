"""Codex native add-on installation verification tests."""

from __future__ import annotations

import json
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.models import (
    CatalogPlugin,
    DesiredState,
    ResultState,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    QueueRunner,
    command,
)
from tests.python.manifest_agent._codex_adapter_test_support import (
    desired as desired,
)

ADDON_NAME = "manifest-i-have-adhd"
ADDON_SOURCE = f"./plugins/{ADDON_NAME}"


def _addon_desired(desired: DesiredState) -> DesiredState:
    return replace(
        desired,
        catalog_plugins=(CatalogPlugin(ADDON_NAME, "0.1.0", ADDON_SOURCE),),
    )


def _write_addon_runtime(
    root: Path,
    *,
    hook_command: str = "python3 ${CLAUDE_PLUGIN_ROOT}/hooks/always_on.py",
    script: str = "pass\n",
    guidance: str = "guidance\n",
) -> None:
    (root / "hooks").mkdir(parents=True)
    (root / "guidance").mkdir()
    (root / "hooks/hooks.json").write_text(
        json.dumps(
            {
                "hooks": {
                    "SessionStart": [
                        {"hooks": [{"command": hook_command, "type": "command"}]}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )
    (root / "hooks/always_on.py").write_text(script, encoding="utf-8")
    (root / "guidance/always-on.md").write_text(guidance, encoding="utf-8")


def _probe_adapter(installed: Path) -> CodexAdapter:
    rows = {
        "installed": [
            {
                "pluginId": f"{ADDON_NAME}@manifest",
                "version": "0.1.0",
                "enabled": True,
                "installedPath": str(installed),
                "source": {"path": str(installed.parent / "marketplace-source")},
            }
        ]
    }
    return CodexAdapter(
        runner=QueueRunner([command(stdout=json.dumps(rows))]),
        which=lambda name: sys.executable if name == "python3" else name,
    )


@pytest.mark.parametrize(
    ("stdout_suffix", "stderr", "expected_state"),
    (
        ("", "", ResultState.READY),
        ("unexpected\n", "", ResultState.BLOCKED),
        ("", "warning\n", ResultState.BLOCKED),
    ),
)
def test_adhd_probe_requires_exact_canonical_stdout_and_empty_stderr(
    desired: DesiredState,
    tmp_path: Path,
    stdout_suffix: str,
    stderr: str,
    expected_state: ResultState,
) -> None:
    installed = tmp_path / "installed-addon"
    guidance = "Canonical guidance."
    expected_stdout = f"Manifest ADHD guidance v0.1.0\n\n{guidance}\n"
    _write_addon_runtime(
        installed,
        script=(
            "import sys\n"
            f"sys.stdout.write({(expected_stdout + stdout_suffix)!r})\n"
            f"sys.stderr.write({stderr!r})\n"
        ),
        guidance=guidance,
    )
    shutil.copytree(installed, desired.release_root / f"plugins/{ADDON_NAME}")

    result = _probe_adapter(installed).probe_adhd_hook(_addon_desired(desired))

    assert result.state is expected_state


def test_adhd_probe_rejects_symlinked_installed_root(
    desired: DesiredState, tmp_path: Path
) -> None:
    actual = tmp_path / "actual-addon"
    _write_addon_runtime(actual)
    installed = tmp_path / "installed-addon"
    installed.symlink_to(actual)

    result = _probe_adapter(installed).probe_adhd_hook(_addon_desired(desired))

    assert result.state is ResultState.BLOCKED
    assert "missing or unsafe" in result.errors[0]


def test_adhd_probe_rejects_unregistered_direct_launcher(
    desired: DesiredState, tmp_path: Path
) -> None:
    installed = tmp_path / "installed-addon"
    _write_addon_runtime(
        installed,
        hook_command="python3 hooks/other.py",
    )

    result = _probe_adapter(installed).probe_adhd_hook(_addon_desired(desired))

    assert result.state is ResultState.BLOCKED
    assert "missing or unsafe" in result.errors[0]


def test_adhd_probe_rejects_tampered_installed_artifacts(
    desired: DesiredState, tmp_path: Path
) -> None:
    desired_root = desired.release_root / "plugins/manifest-i-have-adhd"
    installed = tmp_path / "installed-addon"
    for root in (desired_root, installed):
        _write_addon_runtime(
            root,
            script="print('Manifest ADHD guidance v0.1.0\\n\\ntrusted\\n')\n",
            guidance="trusted\n",
        )
    (installed / "guidance/always-on.md").write_text("tampered\n", encoding="utf-8")

    result = _probe_adapter(installed).probe_adhd_hook(_addon_desired(desired))

    assert result.state is ResultState.BLOCKED
    assert "failed authentication" in result.errors[0]
