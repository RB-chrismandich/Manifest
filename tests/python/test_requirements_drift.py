"""CI pin parity: requirements-*.txt must match configs/claude/uv.lock groups."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]
UV_LOCK = REPO_ROOT / "configs/claude/uv.lock"

REQUIREMENTS_FILES: dict[Path, set[str] | None] = {
    REPO_ROOT / "tests/requirements-runtime.txt": None,  # manifest-runtime core deps
    REPO_ROOT / "tests/requirements-smoke.txt": {"smoke"},
    REPO_ROOT / "tests/requirements-smoke-agent.txt": {"smoke-agent"},
}


def _load_uv_lock() -> tuple[dict[str, str], dict[str, set[str]]]:
    data = tomllib.loads(UV_LOCK.read_text(encoding="utf-8"))
    versions = {pkg["name"]: pkg["version"] for pkg in data["package"]}

    groups: dict[str, set[str]] = {"core": set()}
    for pkg in data["package"]:
        if pkg["name"] != "manifest-runtime":
            continue
        groups["core"] = {dep["name"] for dep in pkg["dependencies"]}
        dev = pkg.get("dev-dependencies", {})
        for group_name, deps in dev.items():
            groups[group_name] = {dep["name"] for dep in deps}
        break

    if not groups["core"]:
        pytest.fail(f"manifest-runtime entry missing from {UV_LOCK}")

    return versions, groups


def _parse_requirements(path: Path) -> list[Requirement]:
    requirements: list[Requirement] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        requirements.append(Requirement(stripped))
    return requirements


def _normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@pytest.mark.parametrize("req_path,allowed_groups", list(REQUIREMENTS_FILES.items()))
def test_requirements_pins_match_uv_lock(
    req_path: Path, allowed_groups: set[str] | None
) -> None:
    assert req_path.is_file(), f"missing requirements file: {req_path}"

    locked_versions, groups = _load_uv_lock()
    requirements = _parse_requirements(req_path)

    for req in requirements:
        name = _normalize_name(req.name)
        locked_version = locked_versions.get(name)
        assert locked_version is not None, (
            f"{req_path.name}: {req.name} not found in {UV_LOCK.name}"
        )

        locked = Version(locked_version)
        assert locked in req.specifier, (
            f"{req_path.name}: {req.name} locked at {locked_version} "
            f"does not satisfy {req.specifier}"
        )

        if allowed_groups is None:
            assert name in groups["core"], (
                f"{req_path.name}: {req.name} is not a manifest-runtime core dependency"
            )
        else:
            in_group = any(name in groups[g] for g in allowed_groups)
            # PyYAML is core runtime; smoke.txt keeps it for legacy CI installs.
            if req_path.name == "requirements-smoke.txt" and name == "pyyaml":
                in_group = name in groups["core"]
            assert in_group, (
                f"{req_path.name}: {req.name} not in uv.lock groups "
                f"{sorted(allowed_groups)} (or core for pyyaml)"
            )
