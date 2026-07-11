#!/usr/bin/env python3
"""Token benchmark harness: measures token overhead and quality before/after manifest."""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

try:
    from anthropic import AsyncAnthropic

    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False
    AsyncAnthropic = None

try:
    from google import genai
    from google.genai import types as genai_types

    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False
    genai = None
    genai_types = None

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "manifest"
RESULTS_DIR = Path(__file__).parent / "results"

PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4-6": {
        "input": 3.00 / 1_000_000,
        "output": 15.00 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
        "cache_read": 0.30 / 1_000_000,
    },
    "gemini-3-flash-preview": {
        "input": 0.10 / 1_000_000,
        "output": 0.40 / 1_000_000,
    },
}


def compute_cost(record: dict, model: str) -> float | None:
    """Return cost in USD for a single API call record, or None if tokens unavailable."""
    pricing = PRICING.get(model)
    if not pricing:
        return None
    input_tok = record.get("input_tokens")
    output_tok = record.get("output_tokens")
    if input_tok is None or output_tok is None:
        return None
    cache_read = min(record.get("cache_read_tokens") or 0, input_tok)
    regular_input = input_tok - cache_read
    return (
        regular_input * pricing["input"]
        + cache_read * pricing.get("cache_read", 0)
        + output_tok * pricing["output"]
    )


def _system_prompt_for_condition(condition: str, category: str, manifest: str) -> str:
    """Return the system prompt string for a given condition and prompt category.

    before       → empty string (no manifest)
    after        → full manifest
    cached       → full manifest (cache_control handled separately in measure_api_claude)
    tiered       → manifest for humaneval only; empty for all other categories
    compressed   → manifest is already the compressed text; treat like after
    """
    if condition == "before":
        return ""
    if condition == "tiered":
        return manifest if category == "humaneval" else ""
    return manifest  # after, cached, compressed


# Minimal system prompt for the CLI "before" condition.
# Empty string stalls the claude CLI; a terse baseline gives it a valid prompt
# to operate from without any Manifest context injection.
# Provider-neutral by design (#546/G9): only reached for providers with a
# verified system_prompt_flag strategy (see PROVIDER_CLI_CONFIG), but the
# wording itself must not falsely label a non-claude provider as Claude.
CLI_BASELINE_SYSTEM_PROMPT = "You are a helpful AI assistant."


@contextmanager
def isolated_environments(fixtures_dir: Path):
    """Yield (empty_home, manifest_home) as Path objects; clean up on exit.

    Used by the API measurement path: the API calls read system-prompt text
    directly from the fixture files in manifest_home.  The CLI path does NOT
    use HOME isolation; it controls manifest context via --system-prompt flags.
    """
    empty_home = Path(tempfile.mkdtemp(prefix="tbench_empty_"))
    manifest_home = Path(tempfile.mkdtemp(prefix="tbench_manifest_"))
    try:
        if fixtures_dir.exists():
            shutil.copytree(
                fixtures_dir,
                manifest_home,
                dirs_exist_ok=True,
                symlinks=True,
                ignore_dangling_symlinks=True,
            )
        yield empty_home, manifest_home
    finally:
        shutil.rmtree(empty_home, ignore_errors=True)
        shutil.rmtree(manifest_home, ignore_errors=True)


def _error_result(msg: str) -> dict:
    return {
        "error": msg,
        "input_tokens": None,
        "output_tokens": None,
        "cache_creation_tokens": None,
        "cache_read_tokens": None,
        "response_text": None,
        "latency_ms": None,
    }


async def measure_api_claude(
    prompt_text: str, system_prompt: str, model: str, use_cache: bool = False
) -> dict:
    """Call Claude API; return input_tokens, output_tokens, response_text, latency_ms.

    use_cache=True adds cache_control to the system prompt block and extracts
    cache_creation_tokens / cache_read_tokens from the usage response.
    """
    if not HAS_ANTHROPIC:
        return _error_result("anthropic package not installed")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _error_result("ANTHROPIC_API_KEY not set")

    client = AsyncAnthropic(api_key=api_key)

    if use_cache:
        system_arg = [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]
    else:
        system_arg = system_prompt

    t0 = time.time()
    try:
        response = await client.messages.create(
            model=model,
            system=system_arg,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=1024,
        )
        latency_ms = int((time.time() - t0) * 1000)
        usage = response.usage
        return {
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "cache_creation_tokens": getattr(
                usage, "cache_creation_input_tokens", None
            ),
            "cache_read_tokens": getattr(usage, "cache_read_input_tokens", None),
            "response_text": response.content[0].text,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as e:
        return _error_result(str(e))


async def measure_api_gemini(prompt_text: str, system_prompt: str, model: str) -> dict:
    """Call Gemini API; return input_tokens, output_tokens, response_text, latency_ms."""
    if not HAS_GENAI:
        return _error_result("google-genai package not installed")

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    t0 = time.time()
    try:
        client = genai.Client(api_key=api_key) if api_key else genai.Client()
        config = (
            genai_types.GenerateContentConfig(
                system_instruction=system_prompt if system_prompt else None,
                max_output_tokens=1024,
            )
            if genai_types is not None
            else None
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=prompt_text,
            **({"config": config} if config is not None else {}),
        )
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "input_tokens": response.usage_metadata.prompt_token_count,
            "output_tokens": response.usage_metadata.candidates_token_count,
            "response_text": response.text,
            "latency_ms": latency_ms,
            "error": None,
        }
    except Exception as e:
        return _error_result(str(e))


def measure_cli(
    prompt_text: str, cli_config: dict, system_prompt: str | None = None
) -> dict:
    """Run provider CLI binary; capture stdout as response.

    system_prompt controls manifest context injection, gated by the
    provider's system_prompt_flag STRATEGY in cli_config (see
    PROVIDER_CLI_CONFIG) — only providers with a verified injection
    mechanism define one (e.g. claude → "--system-prompt"):
      cli_config has no "system_prompt_flag" → the flag is NEVER appended,
        regardless of system_prompt (no verified mechanism; #546). Callers
        should prefer recording an explicit "unsupported" outcome over
        invoking this function to inject manifest context for such
        providers.
      system_prompt is None                 → no flag (CLI uses its real
        HOME config unchanged).
      system_prompt is ""/"<text>"           → flag appended with that value
        ("before"/"after" conditions), only when a strategy exists.
    Auth uses the real HOME so OAuth credentials are always available.
    """
    binary = cli_config["binary"]
    flags = list(cli_config.get("flags", []))
    system_prompt_flag = cli_config.get("system_prompt_flag")
    if system_prompt is not None and system_prompt_flag:
        flags = [*flags, system_prompt_flag, system_prompt]
    t0 = time.time()
    try:
        result = subprocess.run(
            [binary, *flags, prompt_text],
            capture_output=True,
            text=True,
            timeout=60,
        )
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "response_text": result.stdout.strip(),
            "latency_ms": latency_ms,
            "exit_code": result.returncode,
            "error": None if result.returncode == 0 else result.stderr[:300],
        }
    except subprocess.TimeoutExpired:
        return {
            "response_text": "",
            "latency_ms": 60000,
            "exit_code": -1,
            "error": "timeout",
        }
    except FileNotFoundError:
        return {
            "response_text": "",
            "latency_ms": 0,
            "exit_code": -1,
            "error": f"{binary}: not found",
        }


def write_result(record: dict, run_id: str, results_dir: Path | None = None) -> None:
    """Append a result record as a JSON line to results/<run_id>.jsonl."""
    out_dir = results_dir or RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = out_dir / f"{run_id.replace(':', '-')}.jsonl"
    with open(filename, "a") as f:
        f.write(json.dumps(record) + "\n")


def _read_system_prompt(home_dir: Path, provider: str) -> str:
    """Read the manifest system prompt for a provider from a given home dir."""
    from tests.token_benchmark.benchmarks import MANIFEST_SYSTEM_PROMPT_PATHS

    rel_path = MANIFEST_SYSTEM_PROMPT_PATHS.get(provider)
    if not rel_path:
        return ""
    path = home_dir / rel_path
    return path.read_text() if path.exists() else ""


async def run_benchmark(
    providers: list[str],
    api_only: bool,
    run_id: str,
    cli_only: bool = False,
    conditions: list[str] | None = None,
    fixtures_dir: Path | None = None,
    results_dir: Path | None = None,
    claude_model: str = "claude-sonnet-4-6",
    gemini_model: str = "gemini-3-flash-preview",
) -> list[dict]:
    """Run all benchmark prompts for each provider in the specified conditions."""
    from tests.token_benchmark.benchmarks import BENCHMARKS, PROVIDER_CLI_CONFIG
    from tests.token_benchmark.scorer import score

    active_conditions = conditions or ["before", "after"]
    fdir = fixtures_dir or FIXTURES_DIR

    manifest_prompts = {p: _read_system_prompt(fdir, p) for p in providers}
    compressed_dir = fdir.parent / "fixtures-compressed"
    compressed_prompts = {p: _read_system_prompt(compressed_dir, p) for p in providers}

    records = []

    for provider in providers:
        for prompt in BENCHMARKS:
            for condition in active_conditions:
                if not cli_only and provider in ("claude", "gemini"):
                    if condition == "cached" and provider != "claude":
                        continue
                    if condition == "compressed" and not compressed_prompts.get(
                        provider
                    ):
                        continue

                    manifest = (
                        compressed_prompts[provider]
                        if condition == "compressed"
                        else manifest_prompts[provider]
                    )
                    system_prompt = _system_prompt_for_condition(
                        condition, prompt.category, manifest
                    )
                    use_cache = condition == "cached"

                    if provider == "claude":
                        api_result = await measure_api_claude(
                            prompt.text,
                            system_prompt,
                            claude_model,
                            use_cache=use_cache,
                        )
                        if use_cache and not api_result.get("error"):
                            api_result = await measure_api_claude(
                                prompt.text, system_prompt, claude_model, use_cache=True
                            )
                        model_used = claude_model
                    else:
                        api_result = await measure_api_gemini(
                            prompt.text, system_prompt, gemini_model
                        )
                        model_used = gemini_model

                    quality = (
                        score(api_result.get("response_text") or "", prompt)
                        if not api_result.get("error")
                        else None
                    )
                    cost = compute_cost(api_result, model_used)
                    record = {
                        "run_id": run_id,
                        "provider": provider,
                        "model": model_used,
                        "condition": condition,
                        "category": prompt.category,
                        "prompt_id": prompt.prompt_id,
                        "input_tokens": api_result.get("input_tokens"),
                        "output_tokens": api_result.get("output_tokens"),
                        "cache_creation_tokens": api_result.get(
                            "cache_creation_tokens"
                        ),
                        "cache_read_tokens": api_result.get("cache_read_tokens"),
                        "quality_score": quality,
                        "response_text": (api_result.get("response_text") or "")[:200],
                        "latency_ms": api_result.get("latency_ms"),
                        "source": "api",
                        "error": api_result.get("error"),
                        "cost_usd": cost,
                    }
                    write_result(record, run_id, results_dir)
                    records.append(record)
                    cost_str = f" cost=${cost:.6f}" if cost is not None else ""
                    print(
                        f"  [{provider}][api][{condition}][{prompt.prompt_id}] "
                        f"in={record['input_tokens']} out={record['output_tokens']}"
                        f"{cost_str}",
                        flush=True,
                    )

                if not api_only and provider in PROVIDER_CLI_CONFIG:
                    if condition not in ("before", "after"):
                        continue
                    cli_config = PROVIDER_CLI_CONFIG[provider]

                    if not cli_config.get("system_prompt_flag"):
                        # No verified system-prompt injection mechanism for
                        # this provider (e.g. agy 1.1.1 has no --system-prompt
                        # flag; gemini's is unverified). Recording an explicit
                        # "unsupported" outcome — distinct from "error" and
                        # from a scored row — rather than invoking the CLI
                        # with a baseline/manifest prompt it cannot honor, or
                        # falsely labeling it as Claude (#546).
                        record = {
                            "run_id": run_id,
                            "provider": provider,
                            "model": None,
                            "condition": condition,
                            "category": prompt.category,
                            "prompt_id": prompt.prompt_id,
                            "input_tokens": None,
                            "output_tokens": None,
                            "cache_creation_tokens": None,
                            "cache_read_tokens": None,
                            "quality_score": None,
                            "response_text": None,
                            "latency_ms": None,
                            "source": "cli",
                            "error": None,
                            "unsupported": True,
                            "cost_usd": None,
                        }
                        write_result(record, run_id, results_dir)
                        records.append(record)
                        continue

                    cli_sp = (
                        CLI_BASELINE_SYSTEM_PROMPT
                        if condition == "before"
                        else manifest_prompts[provider]
                    )
                    cli_result = measure_cli(
                        prompt.text, cli_config, system_prompt=cli_sp
                    )
                    quality = (
                        score(cli_result.get("response_text") or "", prompt)
                        if not cli_result.get("error")
                        else None
                    )
                    record = {
                        "run_id": run_id,
                        "provider": provider,
                        "model": None,
                        "condition": condition,
                        "category": prompt.category,
                        "prompt_id": prompt.prompt_id,
                        "input_tokens": None,
                        "output_tokens": None,
                        "cache_creation_tokens": None,
                        "cache_read_tokens": None,
                        "quality_score": quality,
                        "response_text": (cli_result.get("response_text") or "")[:200],
                        "latency_ms": cli_result.get("latency_ms"),
                        "source": "cli",
                        "error": cli_result.get("error"),
                        "unsupported": False,
                        "cost_usd": None,
                    }
                    write_result(record, run_id, results_dir)
                    records.append(record)

    return records


def sync_fixtures(
    source_home: Path | None = None,
    fixtures_dir: Path | None = None,
    compression: int | None = None,
) -> None:
    """Copy live manifest configs into fixtures/manifest/ snapshot.

    If compression is given (e.g. 50), also write a compressed fixture at
    fixtures/../fixtures-compressed/ containing the first compression% of lines
    from CLAUDE.md.
    """
    src = source_home or Path.home()
    dst = fixtures_dir or FIXTURES_DIR

    for rel in (".claude/CLAUDE.md", ".claude/settings.json", ".gemini/GEMINI.md"):
        source = src / rel
        dest = dst / rel
        if source.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
            print(f"  synced {rel}")
        else:
            print(f"  skip {rel} (not found at {source})")

    # Antigravity has no system prompt injection (MANIFEST_SYSTEM_PROMPT_PATHS["antigravity"] = None)
    # so its IDE installation does not need to be snapshotted; the empty dir marker suffices.
    print("  skip .antigravity/ (no system prompt injection configured)")

    if compression is not None:
        claude_src = dst / ".claude" / "CLAUDE.md"
        if claude_src.exists():
            all_lines = claude_src.read_text().splitlines()
            keep = max(1, len(all_lines) * compression // 100)
            compressed_dst = (
                dst.parent / "fixtures-compressed" / ".claude" / "CLAUDE.md"
            )
            compressed_dst.parent.mkdir(parents=True, exist_ok=True)
            compressed_dst.write_text("\n".join(all_lines[:keep]))
            print(
                f"  compressed fixture: {keep}/{len(all_lines)} lines → {compressed_dst}"
            )
        else:
            print(
                f"  skip compression: {claude_src} not found (run without --compression first to sync)"
            )


def missing_api_sdks(providers: list[str]) -> list[str]:
    """Return the SDK packages required for the requested API providers but
    not importable in this environment (#547). Antigravity has no API path."""
    missing = []
    if "claude" in providers and not HAS_ANTHROPIC:
        missing.append("anthropic (claude API path)")
    if "gemini" in providers and not HAS_GENAI:
        missing.append("google-genai (gemini API path)")
    return missing


def main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Token benchmark harness")
    parser.add_argument("--providers", default="claude,gemini,antigravity")
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--cli-only", action="store_true")
    parser.add_argument("--sync-fixtures", action="store_true")
    parser.add_argument(
        "--compression",
        type=int,
        default=None,
        help="If set, also write a fixtures-compressed/ with first N%% of lines",
    )
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--claude-model", default="claude-sonnet-4-6")
    parser.add_argument("--gemini-model", default="gemini-3-flash-preview")
    parser.add_argument(
        "--conditions",
        default="before,after",
        help="Comma-separated conditions to run: before,after,cached,tiered,compressed",
    )
    args = parser.parse_args(argv)

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]

    # Hard-fail before any writes: an API-path run without its SDK previously
    # "succeeded" in seconds while appending 40 junk error rows (#547).
    if not args.report_only and not args.cli_only:
        missing = missing_api_sdks(providers)
        if missing:
            print(
                "harness: API path requested but required SDK(s) are not "
                "importable: " + "; ".join(missing) + ". Install them via "
                "`uv run --group benchmark ...` or rerun with --cli-only.",
                file=sys.stderr,
            )
            raise SystemExit(2)

    if args.sync_fixtures:
        print("Syncing fixtures from live home...")
        sync_fixtures(compression=args.compression)

    if not args.report_only:
        from datetime import datetime

        run_id = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        mode = (
            "cli-only"
            if args.cli_only
            else ("api-only" if args.api_only else "api+cli")
        )
        print(f"Running benchmark: providers={providers}, mode={mode}, run_id={run_id}")
        _valid = {"before", "after", "cached", "tiered", "compressed"}
        conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
        _bad = [c for c in conditions if c not in _valid]
        if _bad:
            parser.error(
                f"Unknown conditions: {', '.join(_bad)}. Valid: {', '.join(sorted(_valid))}"
            )
        records = asyncio.run(
            run_benchmark(
                providers=providers,
                api_only=args.api_only,
                cli_only=args.cli_only,
                conditions=conditions,
                run_id=run_id,
                claude_model=args.claude_model,
                gemini_model=args.gemini_model,
            )
        )
        print(f"Done. {len(records)} records written to {RESULTS_DIR}/{run_id}.jsonl")

    print("Regenerating TOKEN_BENCHMARK.md...")
    from tests.token_benchmark.reporter import update_report

    update_report(RESULTS_DIR, REPO_ROOT / "docs" / "TOKEN_BENCHMARK.md")
    print("Done.")


if __name__ == "__main__":
    main()
