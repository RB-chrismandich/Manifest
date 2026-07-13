"""Project verification gate — runs before critics ever see a candidate
(FR-009; research D8).

Auto-detects the target repo's own gates when --verify-cmd is omitted; a repo
with no detectable gates records a disclosed skip (FR-009's "where they exist").
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class VerificationResult:
    ran: bool
    passed: bool
    cmds: list = field(default_factory=list)
    output_path: str | None = None

    def to_dict(self) -> dict:
        return {
            "ran": self.ran,
            "passed": self.passed,
            "cmds": self.cmds,
            "output_path": self.output_path,
        }


def detect_cmds(repo_root: str | Path) -> list[str]:
    repo = Path(repo_root)
    cmds: list[str] = []
    if (repo / "tests" / "bats").is_dir():
        cmds.append("bats tests/bats/")
    if (repo / "tests" / "python").is_dir() or (repo / "pyproject.toml").is_file():
        cmds.append("pytest")
    package_json = repo / "package.json"
    if package_json.is_file():
        try:
            content = package_json.read_text(encoding="utf-8")
            if '"test"' in content:
                scripts = json.loads(content).get("scripts", {})
            else:
                scripts = {}
        except (json.JSONDecodeError, OSError):
            scripts = {}
        if scripts.get("test"):
            cmds.append("npm test -s")
    makefile = repo / "Makefile"
    if makefile.is_file():
        try:
            content = makefile.read_text(encoding="utf-8")
            if "\ntest" in content or content.startswith("test"):
                has_test = re.search(r"^test\s*:", content, re.M)
            else:
                has_test = None
        except OSError:
            has_test = None
        if has_test:
            cmds.append("make test")
    return cmds


def _default_command_runner_factory(repo_root, timeout):
    def run_cmd(cmd: str) -> tuple[int, str]:
        argv = shlex.split(cmd)
        try:
            proc = subprocess.run(
                argv,
                shell=False,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return 124, f"verification command timed out: {cmd}\n"
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")

    return run_cmd


def run_verification(
    repo_root,
    verify_cmd: str | None,
    log_path: str | Path,
    timeout: float | None = None,
    command_runner=None,
) -> VerificationResult:
    """Run the project's gates in sequence, logging output; stop at first failure.

    When ``verify_cmd`` is set, it is parsed as a simple argv string via
    :func:`shlex.split` (``shell=False``). Shell metacharacters such as
    ``&&``, ``|``, and ``;`` are not interpreted — they become literal
    arguments. Use injectable ``command_runner`` if compound shell is required.
    """
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    cmds = [verify_cmd] if verify_cmd else detect_cmds(repo_root)

    if not cmds:
        log_path.write_text(
            "No verification gates detected for this repository — skip recorded "
            "and disclosed (FR-009).\n"
        )
        return VerificationResult(ran=False, passed=True, output_path=str(log_path))

    run_cmd = command_runner or _default_command_runner_factory(repo_root, timeout)
    executed: list[str] = []
    passed = True
    with log_path.open("w", encoding="utf-8") as log:
        for cmd in cmds:
            executed.append(cmd)
            log.write(f"$ {cmd}\n")
            returncode, output = run_cmd(cmd)
            log.write(output)
            if returncode != 0:
                log.write(f"[exit {returncode}]\n")
                passed = False
                break
    return VerificationResult(
        ran=True, passed=passed, cmds=executed, output_path=str(log_path)
    )
