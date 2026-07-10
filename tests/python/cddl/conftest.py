"""Shared fixtures for CDDL tests (feature 482, T002).

Provides the injectable fake runner (research D4 seam), a tmp git-repo factory
(feature branch, clean tree, speckit fixture feature), a tmp state root, and
role-prompt fixtures. All model access in tests goes through FakeRunner —
no network, no real `claude`.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))


class FakeRunner:
    """Scripted stand-in for the `claude -p` subprocess (D4 seam).

    Each queued response is one of: a string (returned as stdout, rc 0), an
    Exception instance (raised — e.g. subprocess.TimeoutExpired), a callable
    (invoked with the prompt, returns stdout), or a (rc, stdout, stderr) tuple.
    Every call is recorded in .calls for prompt/argv assertions.
    """

    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.calls = []

    def __call__(self, argv, prompt, timeout):
        self.calls.append({"argv": list(argv), "prompt": prompt, "timeout": timeout})
        if not self.responses:
            return 1, "", "fake runner exhausted"
        item = self.responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            item = item(prompt)
        if isinstance(item, tuple):
            return item
        return 0, item, ""


def verdict_text(role, decision, findings=None, prefix=""):
    """Build a critic response ending in a well-formed cddl-verdict block."""
    payload = {"role": role, "decision": decision, "findings": findings or []}
    return f"{prefix}```cddl-verdict\n{json.dumps(payload)}\n```\n"


def candidate_text(files, notes="Implemented."):
    """Build an implementer response of cddl-file blocks.

    `files` is a list of (path, content) or (path, content, "delete") tuples.
    """
    parts = [notes, ""]
    for spec in files:
        path, content = spec[0], spec[1]
        kind = "cddl-delete" if len(spec) > 2 and spec[2] == "delete" else "cddl-file"
        parts.append(
            f"```{kind} {path}\n{content}```"
            if content.endswith("\n") or not content
            else f"```{kind} {path}\n{content}\n```"
        )
        parts.append("")
    return "\n".join(parts)


@pytest.fixture
def fake_runner_cls():
    return FakeRunner


@pytest.fixture
def verdict():
    return verdict_text


@pytest.fixture
def candidate():
    return candidate_text


@pytest.fixture
def state_root(tmp_path):
    root = tmp_path / "state"
    root.mkdir()
    return root


def _git(repo, *args):
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "cddl-test",
            "GIT_AUTHOR_EMAIL": "cddl@test",
            "GIT_COMMITTER_NAME": "cddl-test",
            "GIT_COMMITTER_EMAIL": "cddl@test",
        },
    )


@pytest.fixture
def make_repo(tmp_path):
    """Factory: tmp git repo with a committed speckit fixture feature.

    Returns the repo on a checked-out feature branch with a clean tree.
    """

    def factory(name="repo", branch="482-fixture", layout="speckit"):
        repo = tmp_path / name
        (repo / "specs").mkdir(parents=True) if layout == "speckit" else repo.mkdir(
            parents=True
        )
        _git(repo, "init", "-q", "-b", "main")
        if layout == "speckit":
            feat = repo / "specs" / "001-fixture"
            feat.mkdir(parents=True)
            (feat / "spec.md").write_text("# Fixture Spec\nAdd a greeting module.\n")
            (feat / "plan.md").write_text("# Fixture Plan\nOne file: greet.py.\n")
        elif layout == "superpowers":
            specs = repo / "docs" / "superpowers" / "specs"
            plans = repo / "docs" / "superpowers" / "plans"
            specs.mkdir(parents=True)
            plans.mkdir(parents=True)
            (specs / "2026-07-10-fixture-design.md").write_text(
                "# Fixture Design\nAdd a greeting module.\n"
            )
            (plans / "2026-07-10-fixture-plan.md").write_text(
                "# Fixture Plan\nTasks embedded here.\n"
            )
        (repo / "README.md").write_text("fixture repo\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-qm", "init")
        if branch:
            _git(repo, "checkout", "-qb", branch)
        return repo

    return factory


@pytest.fixture
def fixture_repo(make_repo):
    return make_repo()


ROLE_STEMS = {
    "implementer": "implementer",
    "qa_critic": "qa-critic",
    "arch_critic": "arch-critic",
}


def write_role(
    dirpath,
    stem,
    name=None,
    description="Test role",
    model="sonnet",
    body="You are the test role.\n",
    extra_frontmatter="",
):
    text = (
        f"---\nname: {name if name is not None else stem}\n"
        f"description: {description}\nmodel: {model}\n{extra_frontmatter}---\n{body}"
    )
    path = Path(dirpath) / f"{stem}.md"
    path.write_text(text)
    return path


@pytest.fixture
def roles_dir(tmp_path):
    """A valid set of the three fixed role definitions."""
    d = tmp_path / "prompts" / "cddl"
    d.mkdir(parents=True)
    for stem in ROLE_STEMS.values():
        write_role(d, stem)
    return d


@pytest.fixture
def write_role_file():
    return write_role
