import asyncio
import json
import sys
from contextlib import contextmanager
from pathlib import Path

import click

from manifest_cli.doctor import run_doctor
from manifest_cli.runtime import runtime_root, version_line

# A missing optional group is a bootstrap state, not a bug: name the toggle that
# installs it instead of letting a ModuleNotFoundError traceback out of a
# subcommand (design: "Error handling" table, 2026-07-13).
OPTIONAL_DEP_HINTS = {
    "playwright": "smoke deps not installed — re-run ./bootstrap.sh --enable-smoke",
    "browser_use": (
        "browser-use deps not installed — re-run ./bootstrap.sh --enable-browser-use"
    ),
    "anthropic": (
        "Claude SDK not installed — re-run ./bootstrap.sh --enable-claude "
        "(services.claude.enabled)"
    ),
}


@contextmanager
def guarded_imports():
    """Turn an unimportable runtime module into one actionable line + exit 1.

    Covers both halves of the same failure: an optional group that was never
    installed (toggle is off) and a core module missing because `uv sync` was
    interrupted. Only ModuleNotFoundError is caught, so subcommand exit codes and
    real errors still propagate untouched.
    """
    try:
        yield
    except ModuleNotFoundError as exc:
        top = (exc.name or "").split(".")[0]
        hint = OPTIONAL_DEP_HINTS.get(top)
        if hint is None:
            hint = (
                f"home runtime is incomplete — module '{top or exc.name}' is "
                f"missing from {runtime_root()}/.venv; re-run ./bootstrap.sh"
            )
        click.echo(f"manifest: {hint}", err=True)
        raise SystemExit(1) from exc


def _print_version(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if not value or ctx.resilient_parsing:
        return
    click.echo(version_line())
    ctx.exit()


@click.group()
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_print_version,
    # A callback rather than click.version_option: that decorator evaluates its
    # version argument at import time, so every `manifest …` call — including the
    # parallel-agent hot path — paid ~13ms of importlib.metadata lookup for a
    # string it never printed.
    help="Show the runtime version, interpreter, root and deploy provenance.",
)
def cli() -> None:
    """Manifest home-runtime CLI."""


@cli.command(
    "parallel-agent",
    context_settings={"ignore_unknown_options": True},
    add_help_option=False,
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def parallel_agent(args: tuple[str, ...]) -> None:
    with guarded_imports():
        from agents.cli import main as agents_main

        sys.argv = ["manifest parallel-agent", *args]
        raise SystemExit(asyncio.run(agents_main()))


@cli.command(
    "smoke",
    context_settings={"ignore_unknown_options": True},
    add_help_option=False,
)
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def smoke(args: tuple[str, ...]) -> None:
    with guarded_imports():
        from smoke_orchestrator.cli import main as smoke_main

        sys.argv = ["manifest smoke", *args]
        raise SystemExit(smoke_main())


@cli.command("skill-run")
@click.argument("skill_path")
@click.option(
    "--harness",
    required=True,
    type=click.Choice(
        ("claude", "codex", "gemini", "cursor", "antigravity", "agy", "devin")
    ),
)
@click.option(
    "--task-file", type=click.Path(path_type=Path, exists=True, dir_okay=False)
)
@click.option("--model")
@click.option("--model-chain")
@click.option("--model-fallback", type=click.Choice(("auto", "confirm")))
@click.option("--recovery-id")
@click.option("--expected-version", type=int)
@click.option("--fallback-decision", type=click.Choice(("approve", "reject", "auto")))
@click.option("--replacement-tier")
@click.option("--replacement-mode", type=click.Choice(("auto", "confirm")))
@click.option("--non-interactive", is_flag=True)
@click.option("--json", "as_json", is_flag=True)
@click.pass_context
def skill_run_cmd(
    context: click.Context,
    skill_path: str,
    harness: str,
    task_file: Path | None,
    model: str | None,
    model_chain: str | None,
    model_fallback: str | None,
    recovery_id: str | None,
    expected_version: int | None,
    fallback_decision: str | None,
    replacement_tier: str | None,
    replacement_mode: str | None,
    non_interactive: bool,
    as_json: bool,
) -> None:
    """Run one skill through an explicit model-aware native handoff."""
    with guarded_imports():
        from manifest_model_policy.skill_run import (
            SkillRunExecutionError,
            execute_skill_command,
        )

        try:
            outcome = execute_skill_command(
                skill=skill_path,
                harness=harness,
                task_stream=sys.stdin.buffer,
                config_path=runtime_root() / "config/parallel_agent.yml",
                task_file=task_file,
                model=model,
                model_chain=model_chain,
                model_fallback=model_fallback,
                recovery_id=recovery_id,
                expected_version=expected_version,
                fallback_decision=fallback_decision,
                replacement_tier=replacement_tier,
                replacement_mode=replacement_mode,
                non_interactive=non_interactive,
                as_json=as_json,
                confirm_callback=click.confirm,
            )
        except (OSError, SkillRunExecutionError, UnicodeError, ValueError) as error:
            raise click.UsageError(str(error)) from error
    if as_json:
        click.echo(json.dumps(outcome.payload, sort_keys=True))
    else:
        click.echo("\n".join(outcome.text))
    if outcome.exit_code:
        context.exit(outcome.exit_code)


@cli.group()
def skillclaw() -> None:
    """SkillClaw tools."""


def _skillclaw_cmd(module: str, args: tuple[str, ...]) -> None:
    import importlib

    with guarded_imports():
        mod = importlib.import_module(f"skillclaw.{module}")
        raise SystemExit(mod.main(list(args)))


@skillclaw.command("ingest", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_ingest(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("ingest", args)


@skillclaw.command("evolve", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_evolve(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("evolve", args)


@skillclaw.command("promote", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_promote(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("promote", args)


@skillclaw.command("audit", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_audit(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("audit", args)


@skillclaw.command("scrub", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def skillclaw_scrub(args: tuple[str, ...]) -> None:
    _skillclaw_cmd("scrub", args)


@cli.command("doctor")
@click.option(
    "--services",
    type=click.Path(path_type=Path),
    default=None,
    help="services.yml to read (default: <runtime root>/config/services.yml).",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit the check results as JSON for scripted callers.",
)
def doctor_cmd(services: Path | None, as_json: bool) -> None:
    raise SystemExit(run_doctor(services, as_json=as_json))


def main() -> None:
    cli(prog_name="manifest")


if __name__ == "__main__":
    main()
