"""Regression coverage for explicit path-prepend resolver trust context."""

from __future__ import annotations

from pathlib import Path

from manifest_agent.checks import toolchain, toolchain_path_prepend


def test_resolver_forwards_explicit_repository_root(tmp_path: Path):
    """Nested store resolution must not infer repository trust from cwd."""
    repo_root = tmp_path / "repo"
    calls: list[Path] = []

    def resolve_fn(_ref: str, *, lock, store, platform, repo_root: Path):
        del lock, store, platform
        calls.append(repo_root)
        return toolchain.ResolvedTool(
            "demo", tmp_path / "store/bin/demo", None, (), "x" * 64
        )

    context = toolchain_path_prepend.Context(
        resolve_fn=resolve_fn,
        parse_fn=toolchain.parse_store_executable,
        rewrite_argv_fn=toolchain.rewrite_argv,
        with_default_path_fn=lambda entries: entries,
        resolved_tool_cls=toolchain.ResolvedTool,
        blocked_reason_cls=toolchain.BlockedReason,
    )

    toolchain_path_prepend.resolve_engine_refs(
        {"executable": "store:demo/bin/demo", "version_argv": ()},
        context,
        toolchain_path_prepend.ResolutionInputs(
            {}, tmp_path / "store", "linux-x64", repo_root
        ),
    )

    assert calls == [repo_root]


def test_engine_resolution_propagates_blocked_reason(tmp_path: Path) -> None:
    """A blocked store engine is returned before any merged tool is constructed."""
    blocked = toolchain.BlockedReason("toolchain: demo not provisioned")
    context = toolchain_path_prepend.Context(
        resolve_fn=lambda *_args, **_kwargs: blocked,
        parse_fn=toolchain.parse_store_executable,
        rewrite_argv_fn=toolchain.rewrite_argv,
        with_default_path_fn=lambda entries: entries,
        resolved_tool_cls=toolchain.ResolvedTool,
        blocked_reason_cls=toolchain.BlockedReason,
    )

    outcome = toolchain_path_prepend.resolve_engine_refs(
        {"executable": "store:demo/bin/demo", "version_argv": ()},
        context,
        toolchain_path_prepend.ResolutionInputs(
            {}, tmp_path / "store", "linux-x64", tmp_path / "repo"
        ),
    )

    assert outcome is blocked
