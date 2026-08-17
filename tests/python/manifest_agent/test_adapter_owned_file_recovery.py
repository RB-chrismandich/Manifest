"""Revert and recovery semantics for adapter-owned file transitions.

Split from test_adapter_owned_files.py at the 500-line ceiling; that file
keeps capture/archive behaviour, this one keeps the paths that run after a
mutation has already committed and has to be undone or reported.
"""

import os
from pathlib import Path

import pytest

from manifest_agent.adapters.capability_lifecycle import CapabilityAdapterMixin


def test_publish_reverts_swap_when_verification_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A committed exchange must swap back on ANY verification failure.

    The exchange lands before the prior content is inspected. When a concurrent
    actor replaces the entry with a symlink or directory, the inspection raises
    rather than returning a mismatching value; reverting only on the mismatch
    left the caller reporting BLOCKED while the target stayed overwritten.
    """

    class PublishAdapter(CapabilityAdapterMixin):
        name = "cursor"
        adapter_version = "1"

        def __init__(self) -> None:
            self._env = {"HOME": str(tmp_path)}

    adapter = PublishAdapter()
    directory = tmp_path / "state"
    directory.mkdir()
    path = directory / "owned.json"
    original = b'{"original": true}\n'
    path.write_bytes(original)
    path.chmod(0o600)
    temporary = ".owned.json.new"
    (directory / temporary).write_bytes(b'{"replacement": true}\n')
    (directory / temporary).chmod(0o600)

    expected_current = adapter._observe_owned_file(path)
    monkeypatch.setattr(
        PublishAdapter,
        "_open_owned_file_at",
        staticmethod(
            lambda parent_descriptor, name: (_ for _ in ()).throw(
                OSError("entry was replaced concurrently")
            )
        ),
    )

    parent_descriptor = os.open(directory, os.O_RDONLY)
    try:
        with pytest.raises(OSError):
            adapter._publish_owned_file(
                parent_descriptor, path, temporary, expected_current, "file"
            )
    finally:
        os.close(parent_descriptor)

    assert path.read_bytes() == original, "committed swap was not reverted"


def test_expected_uninstall_plugin_ids_requires_every_domain_bundle() -> None:
    """The completeness set is derived, never echoed back from the receipt.

    Passing the receipt's own IDs as the expected set made this comparison a
    tautology that could not fail, so an incomplete receipt authorised removal.
    Mixed bare/suffixed receipts are rejected upstream by each adapter's
    identity check, so only the two uniform forms need to round-trip here.
    """
    from manifest_agent.adapters.capability_receipt import (
        expected_uninstall_plugin_ids,
    )
    from manifest_agent.contracts import ADDON_BUNDLES, DOMAIN_BUNDLES

    bare = tuple(DOMAIN_BUNDLES)
    assert expected_uninstall_plugin_ids(bare) == bare

    suffixed = tuple(f"{name}@manifest" for name in DOMAIN_BUNDLES)
    assert expected_uninstall_plugin_ids(suffixed) == suffixed

    # An opt-in addon is expected only when the receipt records it.
    with_addon = (*bare, ADDON_BUNDLES[0])
    assert expected_uninstall_plugin_ids(with_addon) == with_addon
    assert ADDON_BUNDLES[0] not in expected_uninstall_plugin_ids(bare)

    # A receipt missing a mandatory bundle can never satisfy the expected set.
    incomplete = bare[:-1]
    assert set(expected_uninstall_plugin_ids(incomplete)) != set(incomplete)
    assert expected_uninstall_plugin_ids(()) == bare


def test_quarantine_recovery_reraises_a_filenotfound_original(tmp_path: Path) -> None:
    """A restored slot reports the original error, not stranded-content loss.

    Pins the contract of the recovery path for the awkward case where the
    original failure is itself a FileNotFoundError: the quarantined content is
    renamed back and the caller sees the real cause. It must NOT surface the
    "prior content was retained as ..." message, which would wrongly tell the
    operator their data needs manual recovery.
    """

    from manifest_agent.adapters.capability_owned_files import (
        _recover_quarantined_owned_file,
    )

    directory = tmp_path / "state"
    directory.mkdir()
    path = directory / "owned.json"
    quarantine = ".owned.json.manifest-remove-deadbeef"
    (directory / quarantine).write_bytes(b"prior content\n")

    original = FileNotFoundError("the original failure")
    parent_descriptor = os.open(directory, os.O_RDONLY)
    try:
        with pytest.raises(FileNotFoundError) as caught:
            _recover_quarantined_owned_file(
                parent_descriptor, path, quarantine, original
            )
    finally:
        os.close(parent_descriptor)

    assert caught.value is original, "the original error was swallowed or replaced"
    # And the prior content really was put back, not left in quarantine.
    assert path.read_bytes() == b"prior content\n"
    assert not (directory / quarantine).exists()
