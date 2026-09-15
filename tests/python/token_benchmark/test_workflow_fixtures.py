from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_ROOT = REPO_ROOT / "tests/token_benchmark/workflows/fixtures"
WORKFLOW_IDS = {
    "code-review",
    "documentation",
    "implementation",
    "security-triage",
}
CONDITIONS = {"none", "slim", "full"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe fixture path: {value}")
    return path


def _validate_digest(path: Path, expected: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise ValueError(f"fixture digest mismatch: {path.name}")


def _manifest() -> dict[str, object]:
    return json.loads((FIXTURE_ROOT / "manifest.json").read_text(encoding="utf-8"))


def test_manifest_captures_the_four_workflows_and_three_conditions() -> None:
    manifest = _manifest()

    assert manifest["schema_version"] == 1
    workflows = manifest["workflows"]
    assert set(workflows) == WORKFLOW_IDS
    for workflow_id in WORKFLOW_IDS:
        workflow_root = FIXTURE_ROOT / workflow_id
        task = json.loads((workflow_root / "task.json").read_text(encoding="utf-8"))
        assert set(task["conditions"]) == CONDITIONS
        assert (workflow_root / "slim.md").is_file()
        full_context = FIXTURE_ROOT / _safe_relative(
            workflows[workflow_id]["full_context"]
        )
        assert full_context.is_file()
        assert full_context.name == "SKILL.md"
        assert (workflow_root / "expected.json").is_file()


def test_manifest_hashes_match_every_captured_source_and_fixture_file() -> None:
    manifest = _manifest()

    for source_path, source_record in manifest["sources"].items():
        _safe_relative(source_path)
        captured = FIXTURE_ROOT / _safe_relative(source_record["captured_path"])
        assert captured.is_file()
        _validate_digest(captured, source_record["sha256"])

    for fixture_path, expected in manifest["files"].items():
        fixture = FIXTURE_ROOT / _safe_relative(fixture_path)
        assert fixture.is_file()
        _validate_digest(fixture, expected)

    on_disk = {
        path.relative_to(FIXTURE_ROOT).as_posix()
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    assert on_disk == set(manifest["files"]), (
        f"undigested or stale fixture entries: {on_disk ^ set(manifest['files'])}"
    )


def test_mutated_capture_fails_without_changing_frozen_context(tmp_path: Path) -> None:
    manifest = _manifest()
    workflow = manifest["workflows"]["code-review"]
    captured = FIXTURE_ROOT / _safe_relative(workflow["full_context"])
    original = captured.read_bytes()
    mutated_capture = tmp_path / "SKILL.md"
    mutated_capture.write_bytes(original + b"\nmutated capture\n")

    assert captured.read_bytes() == original
    _validate_digest(captured, manifest["files"][workflow["full_context"]])
    with pytest.raises(ValueError, match="fixture digest mismatch"):
        _validate_digest(mutated_capture, manifest["files"][workflow["full_context"]])


@pytest.mark.parametrize("unsafe", ["/tmp/source", "../source", "a/../../source"])
def test_fixture_paths_reject_absolute_and_traversal_entries(unsafe: str) -> None:
    with pytest.raises(ValueError, match="unsafe fixture path"):
        _safe_relative(unsafe)
