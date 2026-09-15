"""Tests for tests/token_benchmark/workflows/evaluate.py.

Uses the frozen fixtures under tests/token_benchmark/workflows/fixtures/
(read-only) as realistic grading inputs; no network, no model, no real
container runtime.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.workflows.evaluate import (
    ContainerExecutor,
    ContainerLimits,
    ExecutorUnavailable,
    evaluate,
)
from tests.token_benchmark.workflows.fixtures import load_fixture

FIXTURE_ROOT = (
    Path(__file__).resolve().parents[3]
    / "tests"
    / "token_benchmark"
    / "workflows"
    / "fixtures"
)


def _fixture(fixture_id: str) -> dict:
    return load_fixture(FIXTURE_ROOT, fixture_id)


class TestMalformedResponse:
    def test_non_json_response_is_rejected_as_failed(self):
        verdict = evaluate(_fixture("code-review"), "not json at all", executor=None)
        assert verdict["verification"] == "failed"
        assert verdict["failed_criteria"] == ["malformed_json"]

    def test_json_array_response_is_rejected_as_failed(self):
        verdict = evaluate(_fixture("code-review"), "[1, 2, 3]", executor=None)
        assert verdict["verification"] == "failed"
        assert verdict["failed_criteria"] == ["malformed_json"]


class TestCodeReview:
    def test_correct_review_passes(self):
        response = json.dumps(
            {
                "findings": [
                    {
                        "id": "F1",
                        "file": "counter.py",
                        "line": 2,
                        "category": "off_by_one",
                    }
                ],
                "candidate_dispositions": [
                    {"id": "C1", "decision": "refute", "reason": "no SQL involved"}
                ],
            }
        )
        verdict = evaluate(_fixture("code-review"), response, executor=None)
        assert verdict["verification"] == "passed"
        assert verdict["failed_criteria"] == []

    def test_forbidden_category_fails(self):
        response = json.dumps(
            {
                "findings": [
                    {
                        "id": "F1",
                        "file": "counter.py",
                        "line": 2,
                        "category": "off_by_one",
                    },
                    {
                        "id": "F2",
                        "file": "counter.py",
                        "line": 2,
                        "category": "sql_injection",
                    },
                ],
                "candidate_dispositions": [
                    {"id": "C1", "decision": "refute", "reason": "no SQL"}
                ],
            }
        )
        verdict = evaluate(_fixture("code-review"), response, executor=None)
        assert verdict["verification"] == "failed"
        assert "forbidden_categories_absent" in verdict["failed_criteria"]

    def test_invalid_file_identifier_fails(self):
        response = json.dumps(
            {
                "findings": [
                    {
                        "id": "F1",
                        "file": "/etc/passwd",
                        "line": 2,
                        "category": "off_by_one",
                    }
                ],
                "candidate_dispositions": [
                    {"id": "C1", "decision": "refute", "reason": "n/a"}
                ],
            }
        )
        verdict = evaluate(_fixture("code-review"), response, executor=None)
        assert verdict["verification"] == "failed"
        assert "valid_file_identifiers" in verdict["failed_criteria"]


class TestSecurityTriage:
    def test_correct_triage_with_evidence_passes(self):
        response = json.dumps(
            {
                "survived": [
                    {"idx": 1, "reason": "admin endpoint lacks authorization checks"}
                ],
                "refuted": [
                    {
                        "idx": 0,
                        "reason": "resolve() and is_relative_to() bound the path",
                    }
                ],
            }
        )
        verdict = evaluate(_fixture("security-triage"), response, executor=None)
        assert verdict["verification"] == "passed"

    def test_missing_evidence_terms_fails(self):
        response = json.dumps(
            {
                "survived": [{"idx": 1, "reason": "looks bad"}],
                "refuted": [{"idx": 0, "reason": "looks fine"}],
            }
        )
        verdict = evaluate(_fixture("security-triage"), response, executor=None)
        assert verdict["verification"] == "failed"
        assert "evidence_cited" in verdict["failed_criteria"]


class TestDocumentation:
    def _files(self, readme_extra: str = "") -> dict:
        readme = (
            "# minicli\n\n## Requirements\nPython 3.11\n\n"
            "## Commands\ncheck: validate input\nrender: render output\n" + readme_extra
        )
        return {
            "README.md": readme,
            "commands.json": json.dumps(
                {"check": "validate input", "render": "render output"}
            ),
        }

    def test_correct_documentation_passes(self):
        response = json.dumps({"files": self._files()})
        verdict = evaluate(_fixture("documentation"), response, executor=None)
        assert verdict["verification"] == "passed"

    def test_forbidden_claim_fails(self):
        response = json.dumps({"files": self._files("install from PyPI\n")})
        verdict = evaluate(_fixture("documentation"), response, executor=None)
        assert verdict["verification"] == "failed"
        assert "forbidden_claims_absent" in verdict["failed_criteria"]


class FakeExecutor:
    def __init__(self, outcomes):
        self._outcomes = outcomes
        self.calls = []

    def execute(self, solution, entrypoint, cases):
        self.calls.append((solution, entrypoint, cases))
        return self._outcomes


class TestImplementation:
    SOLUTION = "def parse_assignment(v):\n    return v, v\n"

    def test_missing_executor_is_unavailable_not_failed_or_passed(self):
        response = json.dumps({"files": {"solution.py": self.SOLUTION}})
        verdict = evaluate(_fixture("implementation"), response, executor=None)
        assert verdict["verification"] == "unavailable"

    def test_extra_artifact_is_malformed(self):
        response = json.dumps(
            {"files": {"solution.py": self.SOLUTION, "extra.py": "x = 1\n"}}
        )
        verdict = evaluate(
            _fixture("implementation"), response, executor=FakeExecutor([])
        )
        assert verdict["verification"] == "failed"
        assert verdict["failed_criteria"] == ["malformed_json"]

    def test_executor_all_pass_yields_passed(self):
        fixture = _fixture("implementation")
        outcomes = [
            {"criterion_id": cid, "passed": True}
            for cid in fixture["expected"]["public_criteria"]
        ]
        response = json.dumps({"files": {"solution.py": self.SOLUTION}})
        verdict = evaluate(fixture, response, executor=FakeExecutor(outcomes))
        assert verdict["verification"] == "passed"

    def test_executor_reports_only_public_criterion_ids_on_failure(self):
        fixture = _fixture("implementation")
        criteria = fixture["expected"]["public_criteria"]
        outcomes = [
            {"criterion_id": cid, "passed": cid != criteria[0]} for cid in criteria
        ]
        response = json.dumps({"files": {"solution.py": self.SOLUTION}})
        verdict = evaluate(fixture, response, executor=FakeExecutor(outcomes))
        assert verdict["verification"] == "failed"
        assert verdict["failed_criteria"] == [criteria[0]]

    def test_executor_unavailable_exception_is_unavailable_not_failed(self):
        class BrokenExecutor:
            def execute(self, solution, entrypoint, cases):
                raise ExecutorUnavailable("docker: not found")

        response = json.dumps({"files": {"solution.py": self.SOLUTION}})
        verdict = evaluate(
            _fixture("implementation"), response, executor=BrokenExecutor()
        )
        assert verdict["verification"] == "unavailable"
        assert "docker" in verdict["reason"]


class TestContainerExecutor:
    def test_missing_binary_raises_unavailable(self):
        def fake_run(*args, **kwargs):
            raise FileNotFoundError("docker")

        executor = ContainerExecutor("wfbench-fixture:latest", run_command=fake_run)
        with pytest.raises(ExecutorUnavailable):
            executor.execute("def f(x): return x", "f", [])

    def test_missing_image_raises_unavailable(self):
        class FakeResult:
            returncode = 1
            stdout = ""
            stderr = "no such image"

        executor = ContainerExecutor(
            "wfbench-fixture:latest", run_command=lambda *a, **kw: FakeResult()
        )
        with pytest.raises(ExecutorUnavailable):
            executor.execute("def f(x): return x", "f", [])

    def test_run_command_never_pulls_and_is_isolated(self):
        calls = []

        class FakeResult:
            returncode = 0
            stdout = "[]"
            stderr = ""

        def fake_run(command, **kwargs):
            calls.append(command)
            return FakeResult()

        executor = ContainerExecutor("wfbench-fixture:latest", run_command=fake_run)
        outcomes = executor.execute("def f(x): return x", "f", [])
        assert outcomes == []
        assert len(calls) == 2  # probe, then run
        run_command = calls[1]
        assert "--pull" in run_command
        assert run_command[run_command.index("--pull") + 1] == "never"
        assert "--network" in run_command
        assert run_command[run_command.index("--network") + 1] == "none"
        assert "--read-only" in run_command
        assert not any("docker.sock" in str(part) for part in run_command)

    def test_execution_timeout_raises_unavailable(self):
        import subprocess

        def fake_run(command, **kwargs):
            if "inspect" in command:

                class Ok:
                    returncode = 0

                return Ok()
            raise subprocess.TimeoutExpired(cmd=command, timeout=kwargs.get("timeout"))

        executor = ContainerExecutor("wfbench-fixture:latest", run_command=fake_run)
        with pytest.raises(ExecutorUnavailable):
            executor.execute("def f(x): return x", "f", [])


@pytest.mark.skipif(
    os.environ.get("WFBENCH_CONTAINER_SMOKE") != "1",
    reason=(
        "opt-in: set WFBENCH_CONTAINER_SMOKE=1 and WFBENCH_CONTAINER_IMAGE=<ref> "
        "to exercise the real docker command and timeout with harmless code"
    ),
)
class TestContainerExecutorRealSmoke:
    """Opt-in smoke test: validates the actual container command and timeout
    against a real, locally available image with harmless fixture code. Not
    run by default — CI/dev machines are not guaranteed a docker daemon or a
    pre-built wfbench-fixture image (the executor never auto-pulls one)."""

    def test_real_container_grades_a_harmless_public_criterion(self):
        image = os.environ.get("WFBENCH_CONTAINER_IMAGE", "python:3.11-slim")
        executor = ContainerExecutor(image, limits=ContainerLimits(timeout_s=15))
        cases = [
            {
                "criterion_id": "doubles_input",
                "input": 3,
                "expected_result": 6,
                "expected_error": None,
            }
        ]
        outcomes = executor.execute("def f(x):\n    return x * 2\n", "f", cases)
        assert outcomes == [{"criterion_id": "doubles_input", "passed": True}]
