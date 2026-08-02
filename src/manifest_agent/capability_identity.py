"""Static capability identities shared without runtime import dependencies."""

SUPPORTED_EXECUTABLE_IDENTITIES = frozenset({"graphify"})
SUPPORTED_MCP_IDENTITIES = frozenset(
    {"atlassian", "context7", "github", "linear", "sentry", "stitch"}
)


def capability_identity(kind: str, identifier: str) -> str:
    """Return a supported canonical capability identity or fail closed."""
    if kind == "executable" and identifier in SUPPORTED_EXECUTABLE_IDENTITIES:
        return f"executable:{identifier}"
    if kind == "mcp" and identifier in SUPPORTED_MCP_IDENTITIES:
        return f"mcp:{identifier}"
    raise ValueError(f"unsupported owned capability {kind}:{identifier}")
