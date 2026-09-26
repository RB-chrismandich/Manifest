"""Tests for capability identity formatting."""

from unittest import mock

import pytest

from manifest_agent.capability_identity import capability_identity


def test_capability_identity_executable() -> None:
    with mock.patch(
        "manifest_agent.capability_identity.SUPPORTED_EXECUTABLE_IDENTITIES",
        frozenset({"some_executable"}),
    ):
        assert (
            capability_identity("executable", "some_executable")
            == "executable:some_executable"
        )


def test_capability_identity_mcp() -> None:
    assert capability_identity("mcp", "github") == "mcp:github"


def test_capability_identity_unsupported() -> None:
    with pytest.raises(ValueError, match="unsupported owned capability foo:bar"):
        capability_identity("foo", "bar")

    with pytest.raises(
        ValueError, match="unsupported owned capability executable:unknown"
    ):
        capability_identity("executable", "unknown")

    with pytest.raises(ValueError, match="unsupported owned capability mcp:unknown"):
        capability_identity("mcp", "unknown")
