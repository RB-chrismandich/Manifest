"""uv is pinned in three places that must move together.

On GRF runners there is no system python, so the attested ``python_provider``
of every python env is uv's *managed* CPython -- whose build depends on the uv
release. If ``config/toolchain.lock.json``'s ``uv``, the verified bootstrap in
``bootstrap/lib/verified_uv.sh``, and the ``setup-uv`` version of any job that
runs ``manifest provision`` disagree, the provider pin flips between jobs and
the required ``Checks Aggregate (full)`` gate goes red. Bump all three in one
change, then re-dispatch ``Toolchain Attestation`` and re-pin the envs.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "config" / "toolchain.lock.json"
VERIFIED_UV = ROOT / "bootstrap" / "lib" / "verified_uv.sh"
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _lock_uv() -> dict:
    return json.loads(LOCK.read_text(encoding="utf-8"))["tools"]["uv"]


def _shell_case_table(function: str) -> dict[str, str]:
    """Parse `target) echo "<digest>" ;;` arms of one verified_uv.sh function."""
    text = VERIFIED_UV.read_text(encoding="utf-8")
    body = re.search(rf"^{function}\(\) \{{\n(.*?)^\}}", text, re.S | re.M)
    assert body, f"{VERIFIED_UV}: {function} not found"
    return dict(
        re.findall(r'^\s*([\w-]+)\) echo "([0-9a-f]{64})" ;;', body.group(1), re.M)
    )


def _provisioning_setup_uv_versions() -> dict[str, str]:
    """setup-uv `version:` of every ci.yml job that runs `manifest provision`."""
    jobs = yaml.safe_load(CI.read_text(encoding="utf-8"))["jobs"]
    found: dict[str, str] = {}
    for name, job in jobs.items():
        steps = job.get("steps") or []
        if not any("manifest provision" in str(step.get("run", "")) for step in steps):
            continue
        for step in steps:
            if str(step.get("uses", "")).startswith("astral-sh/setup-uv@"):
                found[name] = str((step.get("with") or {}).get("version"))
    return found


def test_verified_bootstrap_installs_the_locked_uv_version() -> None:
    pinned = re.search(
        r"^UV_INSTALLER_PINNED_VERSION=(\S+)$",
        VERIFIED_UV.read_text(encoding="utf-8"),
        re.M,
    )
    assert pinned and pinned.group(1) == _lock_uv()["version"]


@pytest.mark.parametrize(
    ("function", "field"),
    [("_uv_archive_sha256", "sha256"), ("_uv_executable_sha256", "exe_sha256")],
)
def test_verified_bootstrap_digests_match_the_lock(function: str, field: str) -> None:
    table = _shell_case_table(function)
    for platform, record in _lock_uv()["platforms"].items():
        target = re.search(r"uv-(.+)\.tar\.gz$", record["url"]).group(1)
        assert table.get(target) == record[field], f"{platform} ({target}) {field}"


def test_every_provisioning_job_runs_the_locked_uv() -> None:
    versions = _provisioning_setup_uv_versions()
    assert versions, "no ci.yml job both provisions the toolchain and uses setup-uv"
    locked = _lock_uv()["version"]
    drifted = {job: v for job, v in versions.items() if v != locked}
    assert not drifted, f"setup-uv differs from locked uv {locked}: {drifted}"
