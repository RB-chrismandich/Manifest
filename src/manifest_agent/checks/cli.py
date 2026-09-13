"""Click commands for local shared-check execution and aggregation."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import click

from .aggregate import aggregate_results
from .candidate import materialize_candidate
from .registry import load_registry
from .runner import run_profile

_EXITS = {"PASS": 0, "FAIL": 2, "BLOCKED": 3}


def _emit(report: dict, output: Path | None) -> None:
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if output:
        output.write_text(encoded + "\n", encoding="utf-8")
    click.echo(encoded)


def _git_revision(revision: str) -> str:
    result = subprocess.run(
        ("git", "rev-parse", "--verify", f"{revision}^{{commit}}"),
        cwd=Path.cwd(),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"invalid Git revision: {revision}")
    return result.stdout.strip()


def _git_tree(revision: str) -> str:
    result = subprocess.run(
        ("git", "rev-parse", "--verify", f"{revision}^{{tree}}"),
        cwd=Path.cwd(),
        capture_output=True,
        check=False,
        text=True,
    )
    if result.returncode:
        raise ValueError(f"cannot resolve Git tree: {revision}")
    return result.stdout.strip()


@click.command("check")
@click.argument("profile")
@click.option(
    "--project-config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--group")
@click.option("--base", required=True)
@click.option("--json", "as_json", is_flag=True)
@click.option("--output", type=click.Path(path_type=Path))
def check(
    profile: str,
    project_config: Path,
    group: str | None,
    base: str,
    as_json: bool,
    output: Path | None,
) -> None:
    try:
        registry = load_registry(project_config)
        head_sha = _git_revision("HEAD")
        base_sha = _git_revision(base)
        tree_sha = _git_tree("HEAD")
        with tempfile.TemporaryDirectory(prefix="manifest-check-") as temporary:
            candidate = materialize_candidate(
                Path.cwd(),
                Path(temporary) / "candidate",
                head_sha=head_sha,
                tree_sha=tree_sha,
                base_sha=base_sha,
            )
            report = run_profile(registry, profile, group, candidate, {})
    except (OSError, ValueError, RuntimeError) as error:
        report = {
            "schema_version": 1,
            "profile": profile,
            "status": "BLOCKED",
            "diagnostics": [str(error)],
        }
    _emit(report, output)
    raise click.exceptions.Exit(_EXITS[report["status"]])


@click.command("check-aggregate")
@click.argument("profile")
@click.option(
    "--project-config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--results-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--context",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--json", "as_json", is_flag=True)
@click.option("--output", type=click.Path(path_type=Path))
def check_aggregate(
    profile: str,
    project_config: Path,
    results_dir: Path,
    context: Path,
    as_json: bool,
    output: Path | None,
) -> None:
    try:
        registry = load_registry(project_config)
        receipts = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in sorted(results_dir.glob("*.json"))
        ]
        if not receipts:
            raise ValueError("no receipt files found")
        report = aggregate_results(
            registry, profile, receipts, json.loads(context.read_text(encoding="utf-8"))
        )
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        report = {
            "schema_version": 1,
            "profile": profile,
            "status": "BLOCKED",
            "diagnostics": [str(error)],
        }
    _emit(report, output)
    raise click.exceptions.Exit(_EXITS[report["status"]])
