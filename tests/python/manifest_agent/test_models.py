"""Public model contracts for the ephemeral Manifest coordinator."""

from dataclasses import fields

import pytest

from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    DesiredState,
    HarnessReceipt,
    HarnessResult,
    InstallationReceipt,
    OwnedEntry,
    ResultState,
)


def test_result_states_are_stable_strings():
    assert [state.value for state in ResultState] == [
        "READY",
        "DEGRADED",
        "BLOCKED",
        "DRIFTED",
    ]


def test_capability_tiers_are_stable_strings():
    assert [tier.value for tier in CapabilityTier] == [
        "required",
        "default",
        "optional",
    ]


@pytest.mark.parametrize(
    "model",
    [
        BundleContract,
        DesiredState,
        OwnedEntry,
        HarnessReceipt,
        HarnessResult,
        InstallationReceipt,
    ],
)
def test_public_records_are_frozen_dataclasses(model):
    assert model.__dataclass_params__.frozen is True


def test_desired_state_fields_are_stable():
    assert [field.name for field in fields(DesiredState)] == [
        "release_version",
        "source_commit",
        "source",
        "release_root",
        "repository_url",
        "source_dirty",
        "archive_sha256",
        "contracts",
        "selected_optional",
        "requested_harnesses",
    ]


def test_receipt_fields_do_not_include_secret_payloads():
    prohibited = {"token", "header", "environment", "credential", "payload"}
    receipt_models = (OwnedEntry, HarnessReceipt, InstallationReceipt)
    assert all(
        prohibited.isdisjoint({field.name for field in fields(model)})
        for model in receipt_models
    )
