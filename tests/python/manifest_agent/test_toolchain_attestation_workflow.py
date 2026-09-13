"""Static contract for the manually dispatched Linux toolchain attestation."""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


def _attestation_job() -> str:
    workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    return workflow.split("  toolchain-attest-linux:\n", maxsplit=1)[1]


def test_dispatch_attestation_uses_exact_head_and_verified_uv() -> None:
    workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    job = _attestation_job()

    assert "  workflow_dispatch:\n" in workflow
    assert "if: github.event_name == 'workflow_dispatch'" in job
    assert "ref: ${{ github.sha }}" in job
    assert "fetch-depth: 0" in job
    assert 'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"' in job
    assert "source bootstrap/lib/verified_uv.sh" in job
    assert "check_uv" in job
    assert 'UV_BIN="${MANIFEST_VERIFIED_UV_BIN:-}"' in job
    assert 'UV_TOKEN="${MANIFEST_VERIFIED_UV_TOKEN:-}"' in job
    assert "manifest_uv_bin" not in job
    for target in (
        "x86_64-unknown-linux-gnu",
        "aarch64-unknown-linux-gnu",
        "aarch64-apple-darwin",
        "x86_64-apple-darwin",
    ):
        assert target in job
    assert "MANIFEST_VERIFIED_UV_BIN=" in job
    assert "MANIFEST_VERIFIED_UV_TOKEN=" in job
    assert '"$MANIFEST_VERIFIED_UV_BIN" sync --frozen --locked' in job


def test_dispatch_attestation_preserves_only_machine_parseable_evidence() -> None:
    job = _attestation_job()

    assert re.search(
        r'"\$MANIFEST_VERIFIED_UV_BIN" run --frozen manifest provision .*--platform linux-x64 '
        r'--store "\$RUNNER_TEMP/manifest-toolchain" --attest-missing --json > "\$report"',
        job,
    )
    assert "set +e" in job
    assert "provision_exit=$?" in job
    assert 'outcome.get("status") != "UNPINNED"' in job
    assert "expected_unpinned" in job
    assert "missing/extra/duplicate attestation outcomes" in job
    assert '"head_sha": os.environ["GITHUB_SHA"]' in job
    assert '"lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest()' in job
    assert '"workflow_run_attempt": os.environ["GITHUB_RUN_ATTEMPT"]' in job
    assert "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02" in job
    assert "retention-days:" in job
    assert "toolchain-attestation-report.json" in job
    assert "toolchain-attestation-metadata.json" in job
