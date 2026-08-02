#!/usr/bin/env python3
"""Invoke one bundle-local CDDL charter through an installed native CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_CHARTER_NAME = re.compile(r"^[a-z][a-z0-9-]*$")
_RUNTIME = Path(__file__).resolve().parents[1]
_CHARTERS = _RUNTIME / "prompts/cddl"
_CONFIG = _RUNTIME / "config/review_models.json"


def _error(message: str) -> None:
    print(f"cddl-invoke: {message}", file=sys.stderr)


def _load_config() -> dict[str, object]:
    try:
        document = json.loads(_CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"invalid adjacent reviewer config: {error}") from error
    if not isinstance(document, dict) or not isinstance(
        document.get("providers"), dict
    ):
        raise ValueError("invalid adjacent reviewer config")
    return document


def _charter_path(name: str) -> Path:
    if not _CHARTER_NAME.fullmatch(name):
        raise ValueError("charter must be a bundle-local name")
    path = _CHARTERS / f"{name}.md"
    if not path.is_file():
        raise ValueError(f"unknown charter {name!r}")
    return path


def _charter_tier(text: str) -> str:
    if not text.startswith("---\n"):
        return "sonnet"
    end = text.find("\n---", 4)
    if end < 0:
        return "sonnet"
    for line in text[4:end].splitlines():
        if line.startswith("model:"):
            return line.partition(":")[2].strip() or "sonnet"
    return "sonnet"


def _available(binary: str) -> bool:
    path = Path(binary)
    if path.is_absolute() or len(path.parts) > 1:
        return path.is_file() and os.access(path, os.X_OK)
    return shutil.which(binary) is not None


def _select_provider(config: dict[str, object]) -> tuple[str, dict[str, object], str]:
    providers = config["providers"]
    assert isinstance(providers, dict)
    selected = os.environ.get("CDDL_INVOKE_PROVIDER", "auto")
    override = os.environ.get("CDDL_INVOKE_CLI")
    order = config.get("provider_order", [])
    names = list(providers) if not isinstance(order, list) else order
    if selected != "auto":
        names = [selected]
    for name in names:
        settings = providers.get(name)
        if not isinstance(name, str) or not isinstance(settings, dict):
            continue
        binary = override or settings.get("binary")
        if isinstance(binary, str) and _available(binary):
            return name, settings, binary
    raise ValueError("no selected native reviewer CLI is available")


def _command(
    provider: str, binary: str, model: str | None, prompt: str
) -> tuple[list[str], str | None]:
    model_args = ["--model", model] if model else []
    if provider == "antigravity":
        return [binary, *model_args, "--print", prompt], None
    if provider == "cursor":
        return [
            binary,
            "--print",
            "--output-format",
            "text",
            "--mode",
            "ask",
            *model_args,
            prompt,
        ], None
    if provider == "gemini":
        gemini_model = ["-m", model] if model else []
        return [binary, *gemini_model, "-p", prompt], None
    if provider == "codex":
        return [binary, "exec", "--color", "never", *model_args, "-"], prompt
    if provider == "claude":
        return [binary, *model_args, "-p"], prompt
    return [binary, *model_args, prompt], None


def _parser() -> argparse.ArgumentParser:
    choices = sorted(path.stem for path in _CHARTERS.glob("*.md"))
    parser = argparse.ArgumentParser(
        description="Invoke a bundle-local CDDL charter: " + ", ".join(choices)
    )
    parser.add_argument("--charter", required=True, help="bundle-local charter name")
    parser.add_argument("--model-tier", default=None)
    parser.add_argument("--timeout", type=int, default=600)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        charter = _charter_path(args.charter).read_text(encoding="utf-8")
        config = _load_config()
        provider, settings, binary = _select_provider(config)
        models = settings.get("models", {})
        tier = args.model_tier or _charter_tier(charter)
        model = models.get(tier) if isinstance(models, dict) else None
        body = sys.stdin.read().strip()
        prompt = f"{charter.rstrip()}\n\n---\n\n{body}\n" if body else charter
        command, stdin = _command(
            provider, binary, model if isinstance(model, str) else tier, prompt
        )
        result = subprocess.run(
            command,
            input=stdin,
            text=True,
            capture_output=True,
            timeout=args.timeout,
            check=False,
        )
    except (OSError, ValueError) as error:
        _error(str(error))
        return 2
    except subprocess.TimeoutExpired:
        _error(f"timed out after {args.timeout}s")
        return 7
    if result.returncode != 0:
        _error(result.stderr.strip() or f"reviewer exited {result.returncode}")
        return 7
    if not result.stdout.strip():
        _error("reviewer returned empty output")
        return 7
    sys.stdout.write(result.stdout)
    if not result.stdout.endswith("\n"):
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
