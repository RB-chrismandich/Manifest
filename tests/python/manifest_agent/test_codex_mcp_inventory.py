"""Codex must observe its own MCP inventory before adding a server.

`CodexAdapter` accepts a `native_mcp_inventory` but the registry constructs it
with none, so `_apply_mcp` saw an empty inventory on every real run, never
matched an already-registered server, and re-ran `codex mcp add`. For an
OAuth-backed server that restarts an interactive authorization flow which cannot
complete under `--non-interactive`, so the command exits 1 and blocks the whole
reconcile even though the server is registered and authenticated.

Cursor already solves this by reading its own native config at the point of use
rather than relying on the (never-populated) injection seam; these tests pin the
same behavior for Codex, reading `codex mcp list --json`.
"""

import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path

import pytest

from manifest_agent.adapters.base import verify_declared_components
from manifest_agent.adapters.codex import CodexAdapter
from manifest_agent.adapters.codex_catalog import (
    component_evidence,
    component_evidence_failures,
)
from manifest_agent.adapters.codex_mcp_inventory import read_codex_mcp_inventory
from manifest_agent.capabilities import CapabilityPlan, McpDefinition
from manifest_agent.capability_runtime import apply_capability_plan
from manifest_agent.contracts import (
    Capabilities,
    CompatibilityStatus,
    Components,
    Provenance,
)
from manifest_agent.models import (
    BundleContract,
    CapabilityTier,
    CommandResult,
    DesiredState,
    HarnessResult,
    MarketplaceSource,
    MarketplaceSourceKind,
    ResultState,
)
from manifest_agent.process import CommandRunner

ENABLED_HTTP = """
[
  {
    "name": "context7",
    "enabled": true,
    "transport": {
      "type": "streamable_http",
      "url": "https://mcp.context7.com/mcp/oauth"
    },
    "auth_status": "o_auth"
  }
]
"""

DISABLED = """
[
  {
    "name": "context7",
    "enabled": false,
    "transport": {"type": "streamable_http", "url": "https://example.invalid/mcp"}
  }
]
"""

DISABLED_WITHOUT_TRANSPORT = """
[
  {"name": "context7", "enabled": false}
]
"""

UNKNOWN_TRANSPORT = """
[
  {
    "name": "context7",
    "enabled": true,
    "transport": {"type": "carrier_pigeon", "url": "https://example.invalid/mcp"}
  }
]
"""

STDIO = """
[
  {
    "name": "context7",
    "enabled": true,
    "transport": {"type": "stdio", "command": "context7", "args": []}
  }
]
"""

WRONG_URL = """
[
  {
    "name": "context7",
    "enabled": true,
    "transport": {
      "type": "streamable_http",
      "url": "https://example.invalid/wrong"
    }
  }
]
"""


class StubRunner(CommandRunner):
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.log: list[list[str]] = []

    def run(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None
    ) -> CommandResult:
        del env
        self.log.append(list(argv))
        return CommandResult(tuple(argv), self.returncode, self.stdout, "")


class RaisingRunner(CommandRunner):
    def run(
        self, argv: Sequence[str], *, env: Mapping[str, str] | None = None
    ) -> CommandResult:
        del argv, env
        raise OSError("codex is not installed")


def test_enabled_http_server_is_observed_with_catalog_transport() -> None:
    """Codex reports `streamable_http`; the catalog spells the same thing `http`.

    `merge_mcp_definitions` requires exact equality, so an unmapped transport
    would be reported as a conflicting definition rather than a match.
    """
    observation = read_codex_mcp_inventory(StubRunner(stdout=ENABLED_HTTP), None)

    assert observation.error is None
    assert observation.conflicts == {}
    assert observation.inventory == {
        "context7": McpDefinition(
            name="context7",
            transport="http",
            url="https://mcp.context7.com/mcp/oauth",
        )
    }


def test_inventory_is_read_from_the_json_listing() -> None:
    runner = StubRunner(stdout=ENABLED_HTTP)

    read_codex_mcp_inventory(runner, None)

    assert runner.log == [["codex", "mcp", "list", "--json"]]


def test_disabled_server_is_observed_as_conflicting() -> None:
    observation = read_codex_mcp_inventory(StubRunner(stdout=DISABLED), None)

    assert observation.error is None
    assert observation.inventory == {}
    assert "disabled" in observation.conflicts["context7"]


def test_disabled_server_without_transport_is_observed_as_conflicting() -> None:
    observation = read_codex_mcp_inventory(
        StubRunner(stdout=DISABLED_WITHOUT_TRANSPORT), None
    )

    assert observation.error is None
    assert "disabled" in observation.conflicts["context7"]


def test_unknown_transport_is_observed_as_conflicting() -> None:
    observation = read_codex_mcp_inventory(StubRunner(stdout=UNKNOWN_TRANSPORT), None)

    assert observation.error is None
    assert observation.inventory == {}
    assert "carrier_pigeon" in observation.conflicts["context7"]


def test_failed_listing_is_observation_unavailable() -> None:
    observation = read_codex_mcp_inventory(StubRunner(returncode=1, stdout=""), None)

    assert observation.inventory == ()
    assert "observation unavailable" in (observation.error or "")


def test_malformed_listing_is_observation_unavailable() -> None:
    observation = read_codex_mcp_inventory(StubRunner(stdout="not json"), None)

    assert observation.inventory == ()
    assert "invalid JSON" in (observation.error or "")


def test_unavailable_codex_is_observation_unavailable() -> None:
    observation = read_codex_mcp_inventory(RaisingRunner(), None)

    assert observation.inventory == ()
    assert "OSError" in (observation.error or "")


def test_failed_observation_is_distinct_from_observed_empty_inventory() -> None:
    failed = read_codex_mcp_inventory(StubRunner(returncode=1), None)
    empty = read_codex_mcp_inventory(StubRunner(stdout="[]"), None)

    assert failed != empty
    assert failed.error is not None
    assert empty.error is None


def _plan(definition: McpDefinition) -> CapabilityPlan:
    return CapabilityPlan(
        required_mcp=(),
        default_mcp=(definition.name,),
        optional_mcp=(),
        required_executables=(),
        default_executables=(),
        optional_executables=(),
        selected_optional=frozenset(),
        mcp_definitions={definition.name: definition},
        executable_definitions={},
    )


CONTEXT7 = McpDefinition(
    name="context7", transport="http", url="https://mcp.context7.com/mcp/oauth"
)


def test_codex_does_not_re_add_an_already_registered_server() -> None:
    """The regression: re-adding restarts OAuth and exits 1 under --non-interactive."""
    runner = StubRunner(stdout=ENABLED_HTTP)

    result = apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        configure_executables=False,
    )

    assert ["codex", "mcp", "add", "context7"] not in [argv[:4] for argv in runner.log]
    assert result.capabilities["mcp:context7"] == "verified"


def test_codex_still_adds_a_server_it_does_not_serve() -> None:
    runner = StubRunner(stdout="[]")

    apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        configure_executables=False,
    )

    assert any(argv[:3] == ["codex", "mcp", "add"] for argv in runner.log)


def test_codex_refuses_to_add_when_inventory_observation_fails() -> None:
    runner = StubRunner(returncode=1)

    result = apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        configure_executables=False,
    )

    assert runner.log == [["codex", "mcp", "list", "--json"]]
    assert result.capabilities["mcp:context7"] == "observation-unavailable"


@pytest.mark.parametrize("listing", [DISABLED, UNKNOWN_TRANSPORT, STDIO])
def test_codex_conflicting_server_state_never_drives_an_add(listing: str) -> None:
    runner = StubRunner(stdout=listing)

    result = apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        configure_executables=False,
    )

    assert runner.log == [["codex", "mcp", "list", "--json"]]
    assert result.capabilities["mcp:context7"] == "conflicting"


def test_codex_wrong_url_is_conflicting_and_never_drives_an_add() -> None:
    runner = StubRunner(stdout=WRONG_URL)

    result = apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        configure_executables=False,
    )

    assert runner.log == [["codex", "mcp", "list", "--json"]]
    assert result.capabilities["mcp:context7"] == "conflicting"


def test_injected_empty_inventory_suppresses_live_codex_fallback() -> None:
    runner = StubRunner(stdout=ENABLED_HTTP)

    result = apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        native_mcp_inventory={},
        configure_executables=False,
    )

    assert runner.log == [
        [
            "codex",
            "mcp",
            "add",
            "context7",
            "--url",
            "https://mcp.context7.com/mcp/oauth",
        ]
    ]
    assert result.capabilities["mcp:context7"] == "installed-by-manifest"


def test_live_codex_inventory_overrides_runtime_remembered_inventory() -> None:
    runner = StubRunner(stdout="[]")
    adapter = CodexAdapter(runner=runner, which=lambda name: name)
    adapter._remember_capabilities(
        _plan(CONTEXT7),
        HarnessResult("codex", ResultState.READY, (), {"mcp:context7": "verified"}),
    )

    result = adapter.apply_capabilities(_plan(CONTEXT7))

    assert runner.log == [
        ["codex", "mcp", "list", "--json"],
        [
            "codex",
            "mcp",
            "add",
            "context7",
            "--url",
            "https://mcp.context7.com/mcp/oauth",
        ],
    ]
    assert result.capabilities["mcp:context7"] == "installed-by-manifest"


def _desired_with_context7() -> DesiredState:
    """A single-bundle release whose contract declares context7 at DEFAULT tier."""
    root = Path(tempfile.mkdtemp())
    (root / "plugins" / "manifest-workspace").mkdir(parents=True)
    contract = BundleContract(
        name="manifest-workspace",
        version="0.2.0",
        description="fixture",
        category="productivity",
        components=Components(
            skills_root="skills",
            skills_include=(),
            agents=(),
            hooks=(),
            guidance=(),
            runtime=(),
        ),
        capabilities=Capabilities(
            mcp={
                CapabilityTier.REQUIRED: (),
                CapabilityTier.DEFAULT: ("context7",),
                CapabilityTier.OPTIONAL: (),
            },
            executables=dict.fromkeys(CapabilityTier, ()),
        ),
        compatibility={"codex": CompatibilityStatus("native")},
        provenance=Provenance("https://example.invalid", "MIT", "LICENSE", "test"),
    )
    return DesiredState(
        release_version="0.2.0",
        source_commit="a" * 40,
        source="fixture",
        marketplace_source=MarketplaceSource(
            MarketplaceSourceKind.LOCAL, str(root), None
        ),
        release_root=root,
        repository_url="https://example.invalid/repo",
        source_dirty=False,
        archive_sha256="b" * 64,
        contracts=(contract,),
        selected_optional=frozenset(),
        requested_harnesses=("codex",),
    )


def test_bundle_scoped_mcp_evidence_uses_what_codex_actually_serves() -> None:
    """Codex plugin rows carry no `mcpServers` key at all.

    Bundle-scoped MCP evidence therefore could never be collected, so a DEFAULT
    tier MCP capability stayed `missing` and the harness never reached READY —
    even once the apply step stopped re-adding the server. Evidence now comes
    from intersecting what the bundle declares with what Codex reports serving.
    """
    desired = _desired_with_context7()
    rows = [
        {
            "pluginId": "manifest-workspace@manifest",
            "installed": True,
            "installedPath": str(desired.bundle_path("manifest-workspace")),
        }
    ]

    evidence = component_evidence(
        desired, rows, lambda _name: None, served_mcp={"context7": CONTEXT7}
    )

    assert "manifest-workspace:mcp:context7" in evidence


def test_bundle_scoped_mcp_evidence_omits_a_server_codex_does_not_serve() -> None:
    desired = _desired_with_context7()
    rows = [
        {
            "pluginId": "manifest-workspace@manifest",
            "installed": True,
            "installedPath": str(desired.bundle_path("manifest-workspace")),
        }
    ]

    evidence = component_evidence(desired, rows, lambda _name: None, served_mcp={})

    assert "manifest-workspace:mcp:context7" not in evidence


def test_bundle_scoped_mcp_evidence_rejects_wrong_catalog_url() -> None:
    desired = _desired_with_context7()
    rows = [
        {
            "pluginId": "manifest-workspace@manifest",
            "installed": True,
            "installedPath": str(desired.bundle_path("manifest-workspace")),
        }
    ]
    wrong = McpDefinition(
        name="context7", transport="http", url="https://example.invalid/wrong"
    )

    evidence = component_evidence(
        desired, rows, lambda _name: None, served_mcp={"context7": wrong}
    )

    assert "manifest-workspace:mcp:context7" not in evidence


def test_wrong_catalog_url_is_reported_as_conflicting_component_evidence() -> None:
    desired = _desired_with_context7()
    observation = read_codex_mcp_inventory(StubRunner(stdout=WRONG_URL), None)
    failures = component_evidence_failures(desired, observation)

    result = verify_declared_components("codex", desired, (), failures)

    assert result.state is ResultState.DEGRADED
    assert result.capabilities["manifest-workspace:mcp:context7"] == "conflicting"
