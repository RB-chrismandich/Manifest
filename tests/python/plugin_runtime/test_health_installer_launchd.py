"""Darwin-only health installer scheduler regressions."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from tests.python.plugin_runtime.health_test_helpers import (
    isolated_env,
    run_script,
)
from tests.python.plugin_runtime.health_test_helpers import (
    repo_root as _repo_root,
)
from tests.python.plugin_runtime.test_health_installer import (
    _copy_health_source,
    _installer,
    _write_health_tool_fakes,
)


@pytest.mark.skipif(sys.platform != "darwin", reason="launchd-specific behavior")
def test_health_installer_does_not_bootout_an_unowned_loaded_label_after_failed_bootstrap(
    tmp_path: Path,
) -> None:
    source_root = _copy_health_source(_repo_root(), tmp_path / "source")
    environment = isolated_env(tmp_path)
    command_log = _write_health_tool_fakes(tmp_path, environment)
    state = tmp_path / "launchd-state"
    state.write_text("unowned\n", encoding="utf-8")
    environment["MANIFEST_TEST_LAUNCHD_STATE"] = str(state)
    launchctl = Path(environment["PATH"].split(os.pathsep, 1)[0]) / "launchctl"
    launchctl.write_text(
        "#!/bin/sh\n"
        'printf "%s\\n" "launchctl $*" >> "$MANIFEST_TEST_COMMAND_LOG"\n'
        'case "$1" in\n'
        '  bootstrap) test ! -e "$MANIFEST_TEST_LAUNCHD_STATE" || exit 36 ;;\n'
        '  bootout) rm -f "$MANIFEST_TEST_LAUNCHD_STATE" ;;\n'
        "esac\n"
        "exit 0\n",
        encoding="utf-8",
    )
    launchctl.chmod(0o755)

    result = run_script(
        _installer(source_root),
        "--source-root",
        str(source_root),
        "--install",
        env=environment,
        cwd=tmp_path,
    )

    log_lines = command_log.read_text(encoding="utf-8").splitlines()
    assert result.returncode == 1
    assert "launchd bootstrap failed" in result.stderr
    assert any(line.startswith("launchctl bootstrap gui/") for line in log_lines)
    assert state.read_text(encoding="utf-8") == "unowned\n"
    assert not any(line.startswith("launchctl bootout ") for line in log_lines)
