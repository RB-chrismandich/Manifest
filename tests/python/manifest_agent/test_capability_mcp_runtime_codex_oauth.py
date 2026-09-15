"""codex-cli 0.153.4's `codex mcp add` starts an immediate OAuth login the
instant a server declares OAuth support, with no flag to skip it -- only
`--oauth-client-registration`, which selects a *strategy* for that same
immediate login, not whether it happens. Under `--non-interactive` the
printed authorize URL can never be opened, so the native process blocks
forever on its own local OAuth callback listener, and `manifest install
--harness codex --non-interactive` never returns.

These tests pin two things: a non-interactive install must never let that
OAuth flow run unbounded, and the resulting capability must land as an
accurate DEGRADED reason naming the interactive-login requirement, not a
hard failure and not a fake success.
"""

from collections.abc import Mapping, Sequence

from manifest_agent.capabilities import CapabilityPlan, McpDefinition
from manifest_agent.capability_runtime import apply_capability_plan
from manifest_agent.models import CommandResult, ResultState
from manifest_agent.process import CommandRunner, CommandTimeoutError

CONTEXT7 = McpDefinition(
    name="context7", transport="http", url="https://mcp.context7.com/mcp"
)


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


class HangingOAuthRunner(CommandRunner):
    """Simulates codex-cli: `mcp list` reports nothing registered yet, then
    `mcp add` prints the real OAuth banner and never returns before the
    caller's bound -- exactly what CommandRunner.run raises
    CommandTimeoutError for."""

    def __init__(self) -> None:
        self.log: list[list[str]] = []
        self.timeouts: list[float | None] = []

    def run(
        self,
        argv: Sequence[str],
        *,
        env: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> CommandResult:
        del env
        self.log.append(list(argv))
        self.timeouts.append(timeout)
        if list(argv[:3]) == ["codex", "mcp", "list"]:
            return CommandResult(tuple(argv), 0, "[]", "")
        if list(argv[:3]) == ["codex", "mcp", "add"]:
            raise CommandTimeoutError(
                tuple(argv),
                timeout or 0.0,
                "Added global MCP server 'context7'.\n"
                "Detected OAuth support. Starting OAuth flow…\n"
                "Authorize `context7` by opening this URL in your browser:\n"
                "https://clerk.context7.com/oauth/authorize?client_id=abc",
                "",
            )
        raise AssertionError(f"unexpected native command: {argv!r}")


class HangingNonOAuthRunner(HangingOAuthRunner):
    """Same shape, but the native process never printed anything OAuth-like
    before the bound elapsed -- an honest "stuck" report, not a fabricated
    OAuth explanation."""

    def run(self, argv, *, env=None, timeout=None):
        del env
        self.log.append(list(argv))
        self.timeouts.append(timeout)
        if list(argv[:3]) == ["codex", "mcp", "list"]:
            return CommandResult(tuple(argv), 0, "[]", "")
        if list(argv[:3]) == ["codex", "mcp", "add"]:
            raise CommandTimeoutError(tuple(argv), timeout or 0.0, "", "")
        raise AssertionError(f"unexpected native command: {argv!r}")


def test_codex_mcp_add_never_blocks_past_a_bound_when_it_hangs() -> None:
    """The regression: an unbounded `codex mcp add` never returns under
    --non-interactive when the server requires OAuth. The runner must always
    be called with an explicit timeout for codex so the caller can detect
    and recover from the hang instead of blocking forever."""
    runner = HangingOAuthRunner()

    apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        configure_executables=False,
    )

    add_calls = [
        (argv, timeout)
        for argv, timeout in zip(runner.log, runner.timeouts, strict=True)
        if argv[:3] == ["codex", "mcp", "add"]
    ]
    assert add_calls, "expected codex mcp add to be attempted"
    for _argv, timeout in add_calls:
        assert timeout is not None and timeout > 0, (
            "codex mcp add must run under an explicit bound so an interactive "
            "OAuth flow cannot block the install indefinitely"
        )


def test_codex_mcp_add_oauth_hang_is_degraded_with_an_accurate_reason() -> None:
    runner = HangingOAuthRunner()

    result = apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        configure_executables=False,
    )

    assert result.state is ResultState.DEGRADED
    assert result.capabilities["mcp:context7"] == "requires-interactive-login"
    (diagnostic,) = result.errors
    assert "oauth" in diagnostic.lower()
    assert "non-interactive" in diagnostic.lower()


def test_codex_mcp_add_generic_hang_is_reported_without_inventing_oauth() -> None:
    """A hang with no OAuth marker in its output must not be misreported as
    an OAuth requirement it never demonstrated."""
    runner = HangingNonOAuthRunner()

    result = apply_capability_plan(
        "codex",
        _plan(CONTEXT7),
        runner=runner,
        which=lambda _name: "/usr/bin/codex",
        configure_executables=False,
    )

    assert result.state is ResultState.DEGRADED
    (diagnostic,) = result.errors
    assert "oauth" not in diagnostic.lower()
    assert "stuck" in diagnostic.lower()
