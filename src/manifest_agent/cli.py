"""Bootstrap-free Manifest lifecycle command surface."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import click

from manifest_agent.models import ResultState
from manifest_agent.service import HARNESS_ORDER, ManifestService, ServiceReport


@click.group()
def cli() -> None:
    """Install and manage Manifest plugin bundles."""


def _lifecycle_options(command: Callable[..., Any]) -> Callable[..., Any]:
    options = (
        click.option(
            "--harness",
            "harnesses",
            multiple=True,
            type=click.Choice((*HARNESS_ORDER, "all"), case_sensitive=False),
            help="Target a harness; repeat or use 'all'.",
        ),
        click.option(
            "--source",
            type=click.Path(path_type=Path, exists=True, file_okay=False),
            help="Use a local verified checkout.",
        ),
        click.option("--release", help="Use an immutable published release."),
        click.option(
            "--with",
            "selected_optional",
            multiple=True,
            help="Select an optional capability; repeat as needed.",
        ),
        click.option(
            "--non-interactive",
            is_flag=True,
            help="Disable prompts and implicit optional capabilities.",
        ),
        click.option("--json", "as_json", is_flag=True, help="Emit stable JSON."),
    )
    for option in reversed(options):
        command = option(command)
    return command


def _service(**options: Any) -> ManifestService:
    source = options.get("source")
    release = options.get("release")
    if source is not None and release is not None:
        raise click.UsageError("--source and --release are mutually exclusive")
    try:
        return ManifestService(
            source=source,
            release=release,
            harnesses=options.get("harnesses", ()),
            selected_optional=options.get("selected_optional", ()),
            non_interactive=options.get("non_interactive", False),
        )
    except ValueError as error:
        raise click.UsageError(str(error)) from error


def _emit(context: click.Context, report: ServiceReport, as_json: bool) -> None:
    if as_json:
        click.echo(json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":")))
    else:
        click.echo(f"{report.operation}: {report.state.value}")
        for name, result in report.harnesses.items():
            click.echo(f"  {name}: {result.state.value}")
            for error in result.errors:
                click.echo(f"    error: {error}")
            for warning in result.warnings:
                click.echo(f"    warning: {warning}")
        for note in report.notes:
            click.echo(f"  note: {note}")
        for error in report.errors:
            click.echo(f"  error: {error}")
    if report.state in {ResultState.BLOCKED, ResultState.DRIFTED}:
        context.exit(1)


@cli.command()
@_lifecycle_options
@click.pass_context
def install(context: click.Context, **options: Any) -> None:
    """Install the selected Manifest release."""
    service = _service(**options)
    _emit(context, service.install(), options["as_json"])


@cli.command()
@_lifecycle_options
def migrate(**options: Any) -> None:
    """Migrate a legacy Manifest installation."""
    _service(**options)
    raise click.ClickException("not implemented")


@cli.command()
@_lifecycle_options
@click.option("--apply", is_flag=True, help="Repair drift owned by Manifest.")
@click.pass_context
def reconcile(context: click.Context, apply: bool, **options: Any) -> None:
    """Inspect or repair the current installation."""
    service = _service(**options)
    _emit(context, service.reconcile(apply=apply), options["as_json"])


@cli.command()
@_lifecycle_options
@click.pass_context
def uninstall(context: click.Context, **options: Any) -> None:
    """Remove coordinator-owned Manifest installation state."""
    service = _service(**options)
    _emit(context, service.uninstall(), options["as_json"])


def main() -> None:
    """Run the console entry point."""
    cli()
