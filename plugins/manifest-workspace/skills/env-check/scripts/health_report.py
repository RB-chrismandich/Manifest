#!/usr/bin/env python3
"""Produce a bounded, local, sanitized weekly harness health report."""
# ruff: noqa: F405, E402, I001

from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from health_report_common import *  # noqa: F403
from health_report_collect import (
    collect_report,
)
from health_report_sanitize import _safe_reason


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    temporary: str | None = None
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{path.name}.", dir=path.parent
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
        os.chmod(path, 0o600)
    finally:
        if temporary is not None:
            with suppress(OSError):
                os.unlink(temporary)


def write_reports(report: Mapping[str, Any], out_dir: Path) -> None:
    """Atomically write latest plus the UTC weekly file and retain twelve."""
    generated = report.get("generated_at")
    if not isinstance(generated, str) or len(generated) < 10:
        raise ValueError("report timestamp is invalid")
    day = generated[:10].replace("-", "")
    if not re.fullmatch(r"[0-9]{8}", day):
        raise ValueError("report timestamp is invalid")
    payload = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    weekly_path = out_dir / f"weekly-{day}.json"
    latest_path = out_dir / "latest.json"
    _atomic_write_bytes(weekly_path, payload)
    _atomic_write_bytes(latest_path, payload)
    completed = sorted(
        (
            path
            for path in out_dir.iterdir()
            if WEEKLY_FILE.fullmatch(path.name) and _safe_regular_file(path)
        ),
        key=lambda path: path.name,
        reverse=True,
    )
    for expired in completed[WEEKLY_RETENTION:]:
        expired.unlink()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the sanitized report")
    parser.add_argument(
        "--harness",
        action="append",
        required=True,
        choices=("claude", "omp"),
        help="requested native harness; repeat for more than one",
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser


def _render_text(report: Mapping[str, Any]) -> str:
    if report.get("status") == "ok":
        return "Weekly health: ok"
    findings = report.get("findings")
    codes = (
        [
            str(item.get("code"))
            for item in findings[:3]
            if isinstance(item, dict) and _safe_reason(item.get("code"))
        ]
        if isinstance(findings, list)
        else []
    )
    return f"Weekly health: degraded ({','.join(codes) or 'unavailable'})"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = collect_report(harnesses=args.harness)
    try:
        write_reports(report, args.out_dir.expanduser().resolve(strict=False))
    except (OSError, ValueError):
        findings = list(report["findings"])
        _add_finding(findings, "report_write_failed", "report")
        findings.sort(
            key=lambda item: (item["component"], item.get("harness", ""), item["code"])
        )
        report = {**report, "status": "degraded", "findings": findings}
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(_render_text(report))
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
