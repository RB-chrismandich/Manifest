"""The coordinator's intentionally small control-plane command surface."""

import click


@click.group()
def cli() -> None:
    """Install and manage Manifest plugin bundles."""


def _not_implemented() -> None:
    raise click.ClickException("not implemented")


@cli.command()
def install() -> None:
    """Install the selected Manifest release."""
    _not_implemented()


@cli.command()
def migrate() -> None:
    """Migrate a legacy Manifest installation."""
    _not_implemented()


@cli.command()
def reconcile() -> None:
    """Inspect or repair the current installation."""
    _not_implemented()


@cli.command()
def uninstall() -> None:
    """Remove coordinator-owned Manifest installation state."""
    _not_implemented()


def main() -> None:
    """Run the console entry point."""
    cli()
