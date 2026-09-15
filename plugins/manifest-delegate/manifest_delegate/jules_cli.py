"""Bounded Jules CLI calls and conservative parsing of its human output.

Contract measured with Jules 0.1.42, 2026-09-07. Unknown output is not success.
OAuth belongs to the vendor CLI; this module never reads credential stores.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
from dataclasses import dataclass

REPOSITORY = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9_.-]+")
SESSION = re.compile(r"[0-9]{1,30}")
_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_AUTH_ERROR = re.compile(
    r"not logged in|unauthenticated|unauthorized|without a valid client|"
    r"forget to login|invalid (?:token|credentials)",
    re.I,
)
_MAX_OUTPUT = 2 * 1024 * 1024


@dataclass(frozen=True)
class CommandResult:
    """Captured command output, capped independently on each stream."""

    returncode: int
    stdout: str
    stderr: str


def run(
    argv: list[str],
    *,
    payload: bytes | None = None,
    timeout: float = 30,
    cwd: str | None = None,
) -> CommandResult:
    """Execute without shell interpretation or unbounded in-memory capture.

    Jules' Node wrapper spawns a Go binary without forwarding signals. A new
    session makes the wrapper and its descendants one killable process group.
    """
    with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=output,
            stderr=errors,
            cwd=cwd,
            start_new_session=True,
        )
        try:
            process.communicate(
                input=payload if payload is not None else b"", timeout=timeout
            )
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                process.wait()
            except OSError:
                process.kill()
            finally:
                process.communicate()
            raise
        output.seek(0)
        errors.seek(0)
        stdout = output.read(_MAX_OUTPUT + 1)
        stderr = errors.read(_MAX_OUTPUT + 1)
    if max(len(stdout), len(stderr)) > _MAX_OUTPUT:
        raise ValueError("Jules output exceeded the capture limit; result unverified")
    return CommandResult(
        process.returncode,
        stdout.decode("utf-8", "replace"),
        stderr.decode("utf-8", "replace"),
    )


_GITHUB_URL_PREFIXES = (
    "https://github.com/",
    "http://github.com/",
    "ssh://git@github.com/",
    "git@github.com:",
)


def normalize_github_repo(value: str) -> str | None:
    """Canonicalize a GitHub owner/repo reference from any accepted form
    (bare `owner/repo`, `https://github.com/owner/repo[.git]`,
    `git@github.com:owner/repo[.git]`, `ssh://git@github.com/owner/repo[.git]`)
    into a lowercase `owner/repo` string, since GitHub repository paths are
    case-insensitive. Returns None when the value does not resolve to a
    two-segment GitHub repository path."""
    text = value.strip()
    lowered = text.lower()
    for prefix in _GITHUB_URL_PREFIXES:
        if lowered.startswith(prefix):
            text = text[len(prefix) :]
            break
    if text.endswith(".git"):
        text = text[: -len(".git")]
    if not REPOSITORY.fullmatch(text):
        return None
    return text.lower()


def auth_error(output: str) -> bool:
    """Detect the CLI's exit-zero authentication failures on diagnostic-shaped
    lines only. A bare owner/repo row is data, never a diagnostic, even when
    the repository name itself contains a word like "unauthorized"."""
    for line in _ANSI.sub("", output).splitlines():
        stripped = line.strip()
        if not stripped or REPOSITORY.fullmatch(stripped):
            continue
        if _AUTH_ERROR.search(stripped):
            return True
    return False


def parse_repositories(output: str) -> set[str]:
    """Require positive owner/repo rows; empty output proves no access."""
    if auth_error(output) or re.search(r"(?im)^\s*error:", output):
        return set()
    return {
        line.strip()
        for line in _ANSI.sub("", output).splitlines()
        if REPOSITORY.fullmatch(line.strip())
    }


def parse_session_id(output: str) -> str | None:
    """Recover only a unique vendor session URL, never an arbitrary number."""
    ids = set(
        re.findall(
            r"https://jules\.google\.com/session/([0-9]{1,30})(?=[\s/?#]|$)",
            _ANSI.sub("", output),
        )
    )
    return next(iter(ids)) if len(ids) == 1 else None


def parse_session_state(output: str, session_id: str) -> str | None:
    """Read the exact ID row and final status column of the measured table."""
    lines = _ANSI.sub("", output).splitlines()
    if not any(
        re.search(r"\bID\s+Description\s+Repo\s+Last active\s+Status\b", line)
        for line in lines
    ):
        return None
    matches = []
    for line in lines:
        columns = re.split(r"\s{2,}", line.strip())
        if len(columns) < 5 or columns[0] != session_id:
            continue
        # Description can contain extra spaces. Anchor interpretation in the
        # three rightmost columns so words in the prompt cannot become status.
        if not re.fullmatch(r"(?:[0-9]+[hms])+ ago|[0-9]+ days? ago", columns[-2]):
            continue
        state = {"Completed": "completed", "Failed": "failed"}.get(columns[-1])
        if columns[-1] in {
            "Queued",
            "Planning",
            "In Progress",
            "Paused",
            "Awaiting Plan Approval",
            "Awaiting User Feedback",
            "Awaiting User F",
            "Awaiting Plan A",
        }:
            state = "remote_pending"
        matches.append(state)
    return matches[0] if len(matches) == 1 else None


def main() -> int:
    """Standalone stdlib auth check for bootstrap, without delegate runtime imports."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Check Jules authentication and repository access"
    )
    parser.add_argument("--auth", action="store_true", required=True)
    parser.parse_args()
    try:
        result = run(["jules", "remote", "list", "--repo"], timeout=10)
        if result.returncode == 0 and parse_repositories(result.stdout + result.stderr):
            return 0
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
