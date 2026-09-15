"""Structural evaluation for the four frozen workflow fixture kinds.

Grading is deterministic and structural — required findings/dispositions,
survived/refuted indices with cited evidence terms, README/command-map
facts, and (for `artifact_implementation`) an isolated container execution
of the generated `solution.py` against public-criterion-labeled hidden
cases. Malformed JSON and invalid file identifiers are rejected as `failed`,
never silently coerced. A missing execution runtime/image is `unavailable`,
never `passed` and never `failed`.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

_RUN_CASES_SCRIPT = """
import json
import os

with open("/work/solution.py", encoding="utf-8") as handle:
    source = handle.read()
with open("/work/cases.json", encoding="utf-8") as handle:
    cases = json.load(handle)

namespace: dict = {}
exec(compile(source, "solution.py", "exec"), namespace)
entrypoint = namespace.get(os.environ["ENTRYPOINT"])

results = []
for case in cases:
    outcome = False
    if callable(entrypoint):
        if case.get("expected_error"):
            try:
                entrypoint(case["input"])
            except Exception as exc:
                outcome = type(exc).__name__ == case["expected_error"]
        else:
            try:
                outcome = entrypoint(case["input"]) == case.get("expected_result")
            except Exception:
                outcome = False
    results.append({"criterion_id": case["criterion_id"], "passed": outcome})

print(json.dumps(results))
""".lstrip()


class ExecutorUnavailable(Exception):
    """Raised when the configured sandbox runtime or image is not available,
    or a run could not be completed inside it. Never implies pass or fail."""


@dataclass(frozen=True)
class ContainerLimits:
    memory_mb: int = 256
    cpus: float = 1.0
    pids: int = 64
    timeout_s: float = 10.0


class ContainerExecutor:
    """Executes generated `solution.py` inside an explicitly configured,
    locally available immutable container image: no network, no
    credentials, unprivileged user, read-only root filesystem, dropped
    capabilities, bounded CPU/memory/processes, and a timeout. Mounts only
    the isolated fixture input read-only; uses container-private tmpfs
    scratch. Never auto-pulls the image (`--pull never`); a missing binary
    or image raises `ExecutorUnavailable` rather than producing a result.
    """

    def __init__(
        self,
        image: str,
        *,
        binary: str = "docker",
        limits: ContainerLimits | None = None,
        run_command=subprocess.run,
    ) -> None:
        self._image = image
        self._binary = binary
        self._limits = limits or ContainerLimits()
        self._run = run_command

    def _probe(self) -> None:
        try:
            result = self._run(
                [self._binary, "image", "inspect", self._image],
                capture_output=True,
                text=True,
                timeout=5,
            )
        except FileNotFoundError as exc:
            raise ExecutorUnavailable(f"{self._binary}: not found") from exc
        if result.returncode != 0:
            raise ExecutorUnavailable(f"{self._image}: image not present locally")

    def execute(self, solution: str, entrypoint: str, cases: list[dict]) -> list[dict]:
        """Run `cases` against `entrypoint` defined in `solution` and return
        one `{"criterion_id", "passed"}` outcome per case."""
        self._probe()
        with tempfile.TemporaryDirectory(prefix="wfbench_fixture_") as scratch:
            input_dir = Path(scratch)
            (input_dir / "solution.py").write_text(solution, encoding="utf-8")
            (input_dir / "cases.json").write_text(json.dumps(cases), encoding="utf-8")
            (input_dir / "run_cases.py").write_text(_RUN_CASES_SCRIPT, encoding="utf-8")
            return self._run_container(input_dir, entrypoint)

    def _run_container(self, input_dir: Path, entrypoint: str) -> list[dict]:
        limits = self._limits
        command = [
            self._binary,
            "run",
            "--rm",
            "--pull",
            "never",
            "--network",
            "none",
            "--read-only",
            "--user",
            "65534:65534",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(limits.pids),
            "--memory",
            f"{limits.memory_mb}m",
            "--cpus",
            str(limits.cpus),
            "--mount",
            f"type=bind,source={input_dir},target=/work,readonly",
            "--tmpfs",
            "/tmp:rw,size=16m",
            "--workdir",
            "/work",
            "--env",
            f"ENTRYPOINT={entrypoint}",
            self._image,
            "python3",
            "/work/run_cases.py",
        ]
        try:
            result = self._run(
                command, capture_output=True, text=True, timeout=limits.timeout_s
            )
        except subprocess.TimeoutExpired as exc:
            raise ExecutorUnavailable(
                f"execution exceeded {limits.timeout_s}s"
            ) from exc
        if result.returncode != 0:
            raise ExecutorUnavailable(
                f"container exited {result.returncode}: {result.stderr[:300]}"
            )
        return json.loads(result.stdout)


def _result(verification: str, failed: list[str], constraints: dict, reason) -> dict:
    return {
        "verification": verification,
        "failed_criteria": failed,
        "constraint_results": constraints,
        "reason": reason,
    }


def _is_valid_file_id(value) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and ".." not in path.parts


def _finding_present(findings: list, required: dict) -> bool:
    return any(
        isinstance(f, dict)
        and f.get("file") == required["file"]
        and f.get("line") == required["line"]
        and f.get("category") == required["category"]
        for f in findings
    )


def _disposition_present(dispositions: list, required: dict) -> bool:
    return any(
        isinstance(d, dict)
        and d.get("id") == required["id"]
        and d.get("decision") == required["decision"]
        for d in dispositions
    )


def _evaluate_code_review(expected: dict, payload: dict) -> dict:
    findings = payload.get("findings")
    dispositions = payload.get("candidate_dispositions")
    if not isinstance(findings, list) or not isinstance(dispositions, list):
        return _result(
            "failed",
            ["malformed_json"],
            {},
            "findings/candidate_dispositions must be arrays",
        )
    valid_files = all(
        _is_valid_file_id(f.get("file")) for f in findings if isinstance(f, dict)
    )
    present_categories = {f.get("category") for f in findings if isinstance(f, dict)}
    results = {
        "valid_file_identifiers": valid_files,
        "required_findings": all(
            _finding_present(findings, req) for req in expected["required_findings"]
        ),
        "forbidden_categories_absent": present_categories.isdisjoint(
            expected["forbidden_categories"]
        ),
        "required_dispositions": all(
            _disposition_present(dispositions, req)
            for req in expected["required_dispositions"]
        ),
    }
    return _verdict_from_results(results)


def _evidence_present(entries: list, idx: int, terms: list[str]) -> bool:
    reason = next(
        (
            e.get("reason", "")
            for e in entries
            if isinstance(e, dict) and e.get("idx") == idx
        ),
        "",
    )
    lowered = reason.lower()
    return all(term.lower() in lowered for term in terms)


def _evaluate_security_triage(expected: dict, payload: dict) -> dict:
    survived = payload.get("survived")
    refuted = payload.get("refuted")
    if not isinstance(survived, list) or not isinstance(refuted, list):
        return _result(
            "failed", ["malformed_json"], {}, "survived/refuted must be arrays"
        )
    survived_idx = {e.get("idx") for e in survived if isinstance(e, dict)}
    refuted_idx = {e.get("idx") for e in refuted if isinstance(e, dict)}
    results = {
        "disposition_correct": survived_idx == set(expected["survived"])
        and refuted_idx == set(expected["refuted"]),
        "evidence_cited": all(
            _evidence_present(survived + refuted, int(idx), terms)
            for idx, terms in expected["required_evidence_terms"].items()
        ),
    }
    return _verdict_from_results(results)


def _evaluate_documentation(expected: dict, payload: dict) -> dict:
    files = payload.get("files")
    if not isinstance(files, dict):
        return _result("failed", ["malformed_json"], {}, "files must be an object")
    readme = files.get("README.md")
    commands_raw = files.get("commands.json")
    if not isinstance(readme, str) or not isinstance(commands_raw, str):
        return _result(
            "failed",
            ["malformed_json"],
            {},
            "README.md/commands.json must be strings",
        )
    try:
        commands = json.loads(commands_raw)
    except json.JSONDecodeError:
        return _result(
            "failed", ["malformed_json"], {}, "commands.json is not valid JSON"
        )
    results = {
        "readme_sections_present": all(
            section in readme for section in expected["readme_sections"]
        ),
        "required_facts_present": all(
            fact in readme for fact in expected["required_facts"]
        ),
        "forbidden_claims_absent": all(
            claim not in readme for claim in expected["forbidden_claims"]
        ),
        "command_map_correct": isinstance(commands, dict)
        and commands == expected["command_map"],
    }
    return _verdict_from_results(results)


def _evaluate_implementation(expected: dict, payload: dict, executor) -> dict:
    files = payload.get("files")
    if not isinstance(files, dict) or set(files) != {"solution.py"}:
        return _result(
            "failed",
            ["malformed_json"],
            {},
            "response must contain exactly one solution.py artifact",
        )
    solution = files["solution.py"]
    if not isinstance(solution, str) or not solution.strip():
        return _result(
            "failed", ["malformed_json"], {}, "solution.py must be nonempty source"
        )
    if executor is None:
        return _result("unavailable", [], {}, "no fixture execution runtime configured")

    cases = [
        {
            "criterion_id": criterion_id,
            "input": case.get("input"),
            "expected_result": case.get("result"),
            "expected_error": case.get("error"),
        }
        for criterion_id, case in zip(
            expected["public_criteria"], expected["hidden_cases"], strict=False
        )
    ]
    try:
        outcomes = executor.execute(solution, expected["required_symbol"], cases)
    except ExecutorUnavailable as exc:
        return _result("unavailable", [], {}, str(exc))

    results = {outcome["criterion_id"]: outcome["passed"] for outcome in outcomes}
    return _verdict_from_results(results, reason_prefix="hidden criteria failed")


def _verdict_from_results(
    results: dict, *, reason_prefix: str = "structural evaluation failed"
) -> dict:
    failed = [name for name, ok in results.items() if not ok]
    verification = "passed" if not failed else "failed"
    reason = None if not failed else f"{reason_prefix}: " + ", ".join(failed)
    return _result(verification, failed, results, reason)


_EVALUATORS = {
    "code_review": lambda expected, payload, executor: _evaluate_code_review(
        expected, payload
    ),
    "security_triage": lambda expected, payload, executor: _evaluate_security_triage(
        expected, payload
    ),
    "documentation": lambda expected, payload, executor: _evaluate_documentation(
        expected, payload
    ),
    "artifact_implementation": _evaluate_implementation,
}


def evaluate(fixture: dict, response: str, *, executor: object | None) -> dict:
    """Grade one model response against a fixture's frozen expected answers.

    Returns `{"verification": "passed"|"failed"|"unavailable",
    "failed_criteria": [...], "constraint_results": {...}, "reason": str|None}`.
    Malformed JSON and invalid file identifiers are graded `failed`, never
    silently coerced or skipped.
    """
    try:
        payload = json.loads(response)
    except (json.JSONDecodeError, TypeError):
        return _result("failed", ["malformed_json"], {}, "response is not valid JSON")
    if not isinstance(payload, dict):
        return _result(
            "failed", ["malformed_json"], {}, "response JSON is not an object"
        )

    kind = fixture["kind"]
    evaluator = _EVALUATORS.get(kind)
    if evaluator is None:
        return _result(
            "failed", ["unknown_fixture_kind"], {}, f"unknown fixture kind: {kind!r}"
        )
    return evaluator(fixture["expected"], payload, executor)
