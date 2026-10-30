"""Offline reviewer-boundary checks; synthetic credentials never reach a provider."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

RUNTIME = Path(__file__).resolve().parents[2] / "plugins/manifest-forge/runtime"


def executable(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)


@pytest.fixture
def gate(tmp_path):
    runtime = tmp_path / "runtime with spaces"
    shutil.copytree(RUNTIME, runtime)
    commands = tmp_path / "commands"
    commands.mkdir()
    packet = tmp_path / "input"
    packet.write_text("ordinary acceptance criteria\n")
    observed = tmp_path / "observed"
    executable(runtime / "bin/git_platform.sh", "printf git")
    executable(commands / "git", 'cat "$TEST_PACKET"')
    executable(
        commands / "reviewer",
        'cp "$1" "$TEST_OBSERVED"\nprintf \'{"tier1":{"passed":true},"tier2":{"concerns":[]},"verdict":"APPROVED"}\'',
    )
    executable(commands / "gitleaks", "printf '[]'")
    env = dict(
        os.environ,
        PATH=f"{commands}:{os.environ['PATH']}",
        TEST_PACKET=str(packet),
        TEST_OBSERVED=str(observed),
        VERIFICATION_GATE_REVIEW_CMD=str(commands / "reviewer"),
        TMPDIR=str(tmp_path),
    )
    return runtime, commands, packet, observed, env


def invoke(gate):
    runtime, _, _, _, env = gate
    result = subprocess.run(
        [str(runtime / "bin/verification_gate.sh"), "review", "42"],
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    return json.loads(result.stdout)


@pytest.mark.parametrize(
    "failure",
    [
        "missing-redactor",
        "nonexecutable-redactor",
        "missing-verifier",
        "scanner-error",
        "scanner-residual",
        "scanner-invalid",
        "scanner-empty",
    ],
)
def test_inconclusive_controls_never_invoke_reviewer(gate, failure):
    runtime, commands, _, observed, _ = gate
    if failure == "missing-redactor":
        (runtime / "bin/audit_log.sh").unlink()
    elif failure == "nonexecutable-redactor":
        (runtime / "bin/audit_log.sh").chmod(0o644)
    elif failure == "missing-verifier":
        (runtime / "python/verification_packet.py").unlink(missing_ok=True)
    else:
        body = {
            "scanner-error": "exit 2",
            "scanner-residual": "printf '[{}]'; exit 1",
            "scanner-invalid": "printf '{}'",
            "scanner-empty": "exit 0",
        }[failure]
        executable(commands / "gitleaks", body)
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()


@pytest.mark.parametrize(
    "field", ['"password"', '"client_secret"', '"api_key"', '"pass\\u0077ord"']
)
def test_quoted_json_credential_is_removed(gate, field):
    _, _, packet, observed, _ = gate
    secret = "synthetic-" + "credential"[::-1]
    packet.write_text(f'+{{{field}: "{secret}", "context": "keep this"}}\n')
    result = invoke(gate)
    assert result.get("reviewer_error") is not True
    assert secret not in observed.read_text()
    assert "keep this" in observed.read_text()


def test_multiline_sensitive_field_blocks_without_handoff(gate):
    _, _, packet, observed, _ = gate
    packet.write_text("+private_key: |\n+  synthetic private contents\n")
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()


def test_clean_large_packet_and_cleanup(gate):
    _, _, packet, observed, env = gate
    packet.write_text("ordinary context\n" * 20000)
    assert invoke(gate).get("reviewer_error") is not True
    assert observed.read_text().endswith(packet.read_text())
    assert not list(Path(env["TMPDIR"]).glob("vgate-*"))


@pytest.mark.parametrize("family", ["cloud", "source-control", "oauth", "private-key"])
def test_real_scanner_rejects_residual_families_and_allow_comments(gate, family):
    scanner = shutil.which("gitleaks")
    if scanner is None:
        pytest.skip("real Gitleaks required for detector integration")
    _, commands, packet, observed, env = gate
    (commands / "gitleaks").unlink()
    (commands / "gitleaks").symlink_to(scanner)
    values = {
        "cloud": "AK" + "IA" + "QWERTYUIOPASDFGH",
        "source-control": "gl" + "pat-" + "AbCdEf0123456789xyZQ",
        "oauth": "gh" + "u_" + "AbCdEf0123456789" * 3,
        "private-key": "-----BEGIN "
        + "RSA PRIVATE KEY-----\n"
        + "synthetic-material\n-----END RSA PRIVATE KEY-----",
    }
    packet.write_text(values[family] + " # gitleaks:allow\n")
    env["GITLEAKS_CONFIG_TOML"] = '[allowlist]\nregexes=[".*"]'
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()


def real_scanner(gate):
    scanner = shutil.which("gitleaks")
    if scanner is None:
        pytest.skip("real Gitleaks required for detector integration")
    _, commands, _, _, _ = gate
    (commands / "gitleaks").unlink()
    (commands / "gitleaks").symlink_to(scanner)


def test_residual_scan_catches_ineffective_redactor(gate):
    real_scanner(gate)
    runtime, _, packet, observed, _ = gate
    executable(runtime / "bin/audit_log.sh", "printf password=" + "tiny"[::-1])
    packet.write_text("ordinary context")
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()


def test_real_scanner_accepts_sanitized_packet(gate):
    real_scanner(gate)
    _, _, packet, observed, _ = gate
    packet.write_text('{"password": "synthetic value", "context": "preserved"}\n')
    assert invoke(gate).get("reviewer_error") is not True
    assert "synthetic value" not in observed.read_text()
    assert "preserved" in observed.read_text()


def test_missing_scanner_blocks(gate):
    _, commands, _, observed, _ = gate
    executable(commands / "gitleaks", "exit 127")
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()


def test_real_scanner_does_not_skip_large_single_line(gate):
    real_scanner(gate)
    _, _, packet, observed, _ = gate
    packet.write_text("x" * (2 * 1024 * 1024) + " " + "AK" + "IA" + "QWERTYUIOPASDFGH")
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()


def test_missing_scanner_configuration_blocks(gate):
    real_scanner(gate)
    runtime, _, _, observed, _ = gate
    (runtime / "config/verification-gitleaks.toml").unlink()
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()


@pytest.mark.parametrize(
    "body",
    [
        "+password = '''\n+synthetic credential value\n+'''\n",
        "+password: &ref |\n+  synthetic credential value\n",
        '+password: "synthetic credential value"\n',
        "+'password': >-\n+  synthetic credential value\n",
        "+export CLIENT_SECRET=first\\\n+second\n",
    ],
)
def test_unstructured_credentials_block_before_label_is_lost(gate, body):
    real_scanner(gate)
    _, _, packet, observed, _ = gate
    packet.write_text(body)
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()


def test_json_escaped_token_is_scanned(gate):
    real_scanner(gate)
    _, _, packet, observed, _ = gate
    value = "AK" + "IA" + "QWERTYUIOPASDFGH"
    encoded = json.dumps({"note": value}).replace("A", "\\u0041")
    packet.write_text("+" + encoded)
    assert invoke(gate)["reviewer_error"] is True
    assert not observed.exists()
