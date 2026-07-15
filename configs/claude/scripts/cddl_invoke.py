#!/usr/bin/env python3
"""Headless CDDL persona invoke — provider-agnostic CLI seam.

Used by ``/spec-implement-loop`` on platforms without native Task sub-agents
(Gemini CLI, Codex, Antigravity, etc.). The orchestrator assembles the dispatch
body; this script prepends the role charter and invokes the configured CLI.

Environment:
  CDDL_INVOKE_PROVIDER — provider key (antigravity, cursor, gemini, codex, claude)
  CDDL_INVOKE_CLI      — binary override (e.g. agy, cursor-agent)

Usage:
  cddl_invoke.py --charter ~/.claude/prompts/cddl/qa-critic.md < dispatch.md
  printf '%s' "$prompt" | cddl_invoke.py --charter PATH [--model-tier sonnet]
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from agents.cli_invoke import (
    invoke_cli_timed,
    resolve_cli_route,
    resolve_role_model_tier,
)
from agents.config import Config


def _err(message: str) -> None:
    print(f"cddl-invoke: {message}", file=sys.stderr)


def _load_charter(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SystemExit(f"cddl-invoke: cannot read charter {path}: {exc}") from exc


def _build_prompt(charter: str, body: str) -> str:
    body = body.strip()
    if body:
        return f"{charter.rstrip()}\n\n---\n\n{body}\n"
    return charter


async def _run(args: argparse.Namespace) -> int:
    config = Config()
    route = resolve_cli_route(
        config,
        section="cddl_invoke",
        env_prefix="CDDL_INVOKE",
        allow_sdk=False,
    )
    if route is None or route.mode != "cli":
        _err(
            "no headless CLI available — install agy/cursor-agent/gemini/codex/claude "
            "or set CDDL_INVOKE_PROVIDER / CDDL_INVOKE_CLI"
        )
        return 6

    charter_path = Path(args.charter).expanduser()
    charter = _load_charter(charter_path)
    body = sys.stdin.read()
    prompt = _build_prompt(charter, body)
    tier = args.model_tier or resolve_role_model_tier(charter_path)

    try:
        output = await invoke_cli_timed(
            route,
            prompt,
            config,
            model_tier=tier,
            timeout=args.timeout,
        )
    except TimeoutError:
        _err(f"timed out after {args.timeout}s")
        return 7
    except RuntimeError as exc:
        _err(str(exc))
        return 7

    sys.stdout.write(output)
    if output and not output.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CDDL headless persona invoke")
    parser.add_argument(
        "--charter",
        required=True,
        help="Role charter markdown (configs/claude/prompts/cddl/*.md)",
    )
    parser.add_argument(
        "--model-tier",
        default=None,
        help="Model tier alias (default: model: from charter frontmatter)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Per-invoke wall clock seconds (default: 600)",
    )
    args = parser.parse_args(argv)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
