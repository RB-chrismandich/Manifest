import asyncio
import sys
from pathlib import Path

import click

from manifest_cli.doctor import run_doctor


@click.group()
def cli() -> None:
    """Manifest home-runtime CLI."""


@cli.command("parallel-agent", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def parallel_agent(args: tuple[str, ...]) -> None:
    from agents.cli import main as agents_main

    sys.argv = ["manifest parallel-agent", *args]
    raise SystemExit(asyncio.run(agents_main()))


@cli.command("smoke", context_settings={"ignore_unknown_options": True})
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def smoke(args: tuple[str, ...]) -> None:
    from smoke_orchestrator.cli import main as smoke_main

    sys.argv = ["manifest smoke", *args]
    raise SystemExit(smoke_main())


@cli.group()
def skillclaw() -> None:
    """SkillClaw tools."""


def _skillclaw_cmd(module: str, args: tuple[str, ...]) -> None:
    import importlib

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
    default=Path.home() / ".claude/config/services.yml",
)
def doctor_cmd(services: Path) -> None:
    raise SystemExit(run_doctor(services))


def main() -> None:
    cli(prog_name="manifest")


if __name__ == "__main__":
    main()
