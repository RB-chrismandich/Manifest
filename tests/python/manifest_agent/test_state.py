import json
import os
import stat
import subprocess
import sys
from contextlib import ExitStack
from dataclasses import replace
from pathlib import Path

import pytest

from manifest_agent.models import HarnessReceipt, InstallationReceipt, OwnedEntry
from manifest_agent.ownership import (
    codex_receipt_ownership_errors,
    graphify_retirement_transaction_proof,
    owned_capability_entry,
)
from manifest_agent.state import (
    RetiredGraphifyTransaction,
    StateError,
    installation_lock,
    read_receipt,
    read_retired_graphify_transaction,
    receipt_digest,
    retired_graphify_transaction_path,
    write_receipt_atomic,
    write_retired_graphify_transaction_atomic,
)

SAMPLE_RECEIPT = InstallationReceipt(
    schema_version=1,
    coordinator_version="0.1.0",
    release_version="1.2.3",
    source_commit="a" * 40,
    source_dirty=False,
    archive_sha256="b" * 64,
    bundle_checksums={"manifest-core": "c" * 64},
    selected_optional=("context7",),
    harnesses={
        "claude": HarnessReceipt(
            harness="claude",
            adapter_version="1",
            native_version="2.0.0",
            plugin_ids=("manifest-core",),
            owned_entries=(
                OwnedEntry(
                    kind="plugin",
                    identifier="manifest-core",
                    ownership_marker="manifest",
                    target_path="/tmp/native/plugin.json",
                    previous_checksum="d" * 64,
                ),
            ),
            capabilities={"plugins.install": "verified"},
            verified=True,
        )
    },
)


def test_receipt_write_is_atomic_private_and_round_trips(tmp_path):
    path = tmp_path / "installation.json"

    write_receipt_atomic(path, SAMPLE_RECEIPT)

    assert read_receipt(path) == SAMPLE_RECEIPT
    assert not list(tmp_path.glob("*.tmp"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_graphify_retirement_transaction_round_trips_strictly(tmp_path) -> None:
    receipt_path = tmp_path / "installation.json"
    path = retired_graphify_transaction_path(receipt_path)
    legacy_digest = receipt_digest(SAMPLE_RECEIPT)
    owned_capability_entry(
        "executable", "graphify", key_path=tmp_path / "ownership.key"
    )
    transaction = RetiredGraphifyTransaction(
        phase="prepared",
        legacy_receipt_digest=legacy_digest,
        legacy_receipt=SAMPLE_RECEIPT,
        target_receipt=SAMPLE_RECEIPT,
        ownership_proof=graphify_retirement_transaction_proof(
            "prepared",
            legacy_digest,
            SAMPLE_RECEIPT,
            SAMPLE_RECEIPT,
            key_path=tmp_path / "ownership.key",
        ),
    )

    write_retired_graphify_transaction_atomic(path, transaction)

    assert read_retired_graphify_transaction(path) == transaction
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_graphify_retirement_transaction_rejects_unknown_fields(tmp_path) -> None:
    path = retired_graphify_transaction_path(tmp_path / "installation.json")
    path.write_text('{"schema_version": 1, "unexpected": true}', encoding="utf-8")

    with pytest.raises(StateError, match="retired Graphify transaction"):
        read_retired_graphify_transaction(path)


def test_state_module_imports_in_a_fresh_interpreter() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "import manifest_agent.state"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_receipt_rejects_secret_fields(tmp_path):
    secret_entry = OwnedEntry(
        kind="mcp",
        identifier="context7",
        ownership_marker="manifest",
        target_path="Authorization: Bearer secret-value",
    )
    harness = replace(SAMPLE_RECEIPT.harnesses["claude"], owned_entries=(secret_entry,))
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": harness})

    with pytest.raises(StateError, match="credential material"):
        write_receipt_atomic(tmp_path / "installation.json", receipt)


def test_receipt_rejects_unlinked_capability_ownership(tmp_path):
    forged = OwnedEntry("mcp", "context7", "manifest", None, None)
    harness = replace(
        SAMPLE_RECEIPT.harnesses["claude"],
        owned_entries=(forged,),
        capabilities={"mcp:context7": "installed-by-manifest"},
    )
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": harness})

    with pytest.raises(StateError, match="ownership authority"):
        write_receipt_atomic(tmp_path / "installation.json", receipt)


def test_receipt_round_trips_linked_capability_ownership(tmp_path):
    harness = replace(
        SAMPLE_RECEIPT.harnesses["claude"],
        owned_entries=(
            owned_capability_entry(
                "mcp",
                "context7",
                key_path=tmp_path / "ownership.key",
            ),
        ),
        capabilities={"mcp:context7": "installed-by-manifest"},
    )
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": harness})
    path = tmp_path / "installation.json"

    write_receipt_atomic(path, receipt)

    assert read_receipt(path) == receipt


def test_receipt_rejects_credential_shaped_capability_keys(tmp_path):
    harness = replace(
        SAMPLE_RECEIPT.harnesses["claude"], capabilities={"api_token": "redacted"}
    )
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": harness})

    with pytest.raises(StateError, match="credential material"):
        write_receipt_atomic(tmp_path / "installation.json", receipt)


@pytest.mark.parametrize(
    "leak",
    [
        "native failed --token super-secret",
        "native failed --api-key API-KEY-VALUE",
        "native failed --API_KEY UNDERSCORE-VALUE",
        "native failed --password=PASSWORD-VALUE",
        "native failed --credential CREDENTIAL-VALUE",
        "native failed --credential=CREDENTIAL-EQUALS-VALUE",
        "native failed --authorization AUTHORIZATION-VALUE",
        "native failed --authorization=AUTHORIZATION-EQUALS-VALUE",
    ],
)
def test_receipt_rejects_cli_flag_credentials(tmp_path, leak):
    harness = replace(
        SAMPLE_RECEIPT.harnesses["claude"],
        verified=False,
        capabilities={"plugins.install": "failed"},
        errors=(leak,),
    )
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": harness})

    with pytest.raises(StateError, match="credential material"):
        write_receipt_atomic(tmp_path / "installation.json", receipt)


def test_partial_receipt_preserves_verified_and_failed_harness_facts(tmp_path):
    failed = HarnessReceipt(
        harness="cursor",
        adapter_version="1",
        native_version="0.50.0",
        plugin_ids=(),
        owned_entries=(),
        capabilities={"plugins.activation": "unsupported"},
        verified=False,
        errors=("native install exited 1: [REDACTED]",),
    )
    receipt = replace(
        SAMPLE_RECEIPT,
        harnesses={"claude": SAMPLE_RECEIPT.harnesses["claude"], "cursor": failed},
    )

    path = tmp_path / "installation.json"
    write_receipt_atomic(path, receipt)
    restored = read_receipt(path)

    assert restored.harnesses["claude"].verified is True
    assert restored.harnesses["cursor"].verified is False
    assert restored.harnesses["cursor"].errors == failed.errors
    assert restored.harnesses["cursor"].capabilities == failed.capabilities


def test_unverified_harness_requires_an_explicit_failure(tmp_path):
    silent_failure = replace(
        SAMPLE_RECEIPT.harnesses["claude"], verified=False, errors=()
    )
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": silent_failure})

    with pytest.raises(StateError, match="explicit error"):
        write_receipt_atomic(tmp_path / "installation.json", receipt)


def test_unverified_harness_cannot_claim_verified_capabilities(tmp_path):
    false_claim = replace(
        SAMPLE_RECEIPT.harnesses["claude"],
        verified=False,
        capabilities={"plugins.install": "verified"},
        errors=("verification failed",),
    )
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": false_claim})

    with pytest.raises(StateError, match="capabilities"):
        write_receipt_atomic(tmp_path / "installation.json", receipt)


@pytest.mark.parametrize("bypass", ["active", "enabled", "installed (unverified)"])
def test_unverified_harness_rejects_unknown_or_success_like_capabilities(
    tmp_path, bypass
):
    false_claim = replace(
        SAMPLE_RECEIPT.harnesses["claude"],
        verified=False,
        capabilities={"plugins.install": bypass},
        errors=("verification failed",),
    )
    receipt = replace(SAMPLE_RECEIPT, harnesses={"claude": false_claim})

    with pytest.raises(StateError, match="capabilities"):
        write_receipt_atomic(tmp_path / "installation.json", receipt)


def test_receipt_reader_rejects_unknown_fields(tmp_path):
    path = tmp_path / "installation.json"
    write_receipt_atomic(path, SAMPLE_RECEIPT)
    document = json.loads(path.read_text(encoding="utf-8"))
    document["access_token"] = "secret"
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(StateError, match="credential material"):
        read_receipt(path)


def test_receipt_reader_rejects_unknown_harness_identity(tmp_path):
    path = tmp_path / "installation.json"
    write_receipt_atomic(path, SAMPLE_RECEIPT)
    document = json.loads(path.read_text(encoding="utf-8"))
    unknown = dict(document["harnesses"]["claude"])
    unknown["harness"] = "future-harness"
    document["harnesses"]["future-harness"] = unknown
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(StateError, match="unsupported receipt harness"):
        read_receipt(path)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("schema_version", 2), "schema version"),
        (("source_commit", "main"), "source commit"),
        (("archive_sha256", "not-a-checksum"), "archive SHA-256"),
        (("bundle_checksums", {"manifest-core": "bad"}), "bundle checksum"),
    ],
)
def test_receipt_reader_rejects_invalid_immutable_identity(tmp_path, mutation, message):
    path = tmp_path / "installation.json"
    write_receipt_atomic(path, SAMPLE_RECEIPT)
    document = json.loads(path.read_text(encoding="utf-8"))
    field, value = mutation
    document[field] = value
    path.write_text(json.dumps(document), encoding="utf-8")

    with pytest.raises(StateError, match=message):
        read_receipt(path)


def test_installation_lock_uses_xdg_state_and_is_nonblocking(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    expected = tmp_path / "manifest" / "install.lock"

    with ExitStack() as stack:
        lock_path = stack.enter_context(installation_lock())
        assert lock_path == expected
        assert expected.exists()
        with pytest.raises(StateError, match="already in progress"):
            stack.enter_context(installation_lock())


def test_atomic_write_cleans_temporary_file_after_replace_failure(
    monkeypatch, tmp_path
):
    path = tmp_path / "installation.json"

    def fail_replace(source: Path, destination: Path):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)

    with pytest.raises(StateError, match="write receipt"):
        write_receipt_atomic(path, SAMPLE_RECEIPT)
    assert not list(tmp_path.glob("*.tmp"))


def test_legacy_codex_receipt_error_names_its_remediation(tmp_path):
    """A pre-authentication receipt must fail closed with an actionable reason.

    Receipts written before Codex receipt authentication existed carry no
    proof. Rejecting them is deliberate, but the operator needs to be told how
    to recover rather than reading it as receipt corruption.
    """
    legacy = HarnessReceipt(
        harness="codex",
        adapter_version="1",
        native_version="2",
        plugin_ids=(),
        owned_entries=(),
        capabilities={},
        verified=True,
    )

    errors = codex_receipt_ownership_errors(legacy, key_path=tmp_path / "ownership.key")

    assert len(errors) == 1
    assert "predates Codex receipt authentication" in errors[0]
    assert "manifest install" in errors[0]
