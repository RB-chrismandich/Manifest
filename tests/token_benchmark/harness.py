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
from typing import Optional

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
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "manifest"
RESULTS_DIR = Path(__file__).parent / "results"


@contextmanager
def isolated_environments(fixtures_dir: Path):
    """Yield (empty_home, manifest_home) as Path objects; clean up on exit."""
    empty_home = Path(tempfile.mkdtemp(prefix="tbench_empty_"))
    manifest_home = Path(tempfile.mkdtemp(prefix="tbench_manifest_"))
    try:
        if fixtures_dir.exists():
            shutil.copytree(fixtures_dir, manifest_home, dirs_exist_ok=True)
        yield empty_home, manifest_home
    finally:
        shutil.rmtree(empty_home, ignore_errors=True)
        shutil.rmtree(manifest_home, ignore_errors=True)


def _error_result(msg: str) -> dict:
    return {"error": msg, "input_tokens": None, "output_tokens": None, "response_text": None, "latency_ms": None}


async def measure_api_claude(prompt_text: str, system_prompt: str, model: str) -> dict:
    """Call Claude API; return input_tokens, output_tokens, response_text, latency_ms."""
    if not HAS_ANTHROPIC:
        return _error_result("anthropic package not installed")

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _error_result("ANTHROPIC_API_KEY not set")

    client = AsyncAnthropic(api_key=api_key)
    t0 = time.time()
    try:
        response = await client.messages.create(
            model=model,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt_text}],
            max_tokens=1024,
        )
        latency_ms = int((time.time() - t0) * 1000)
        return {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
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
        config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            max_output_tokens=1024,
        ) if genai_types is not None else None
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


def measure_cli(prompt_text: str, cli_config: dict, home_dir: Path) -> dict:
    """Run provider CLI binary with HOME overridden; capture stdout as response."""
    binary = cli_config["binary"]
    flags = cli_config.get("flags", [])
    env = os.environ.copy()
    env["HOME"] = str(home_dir)
    t0 = time.time()
    try:
        result = subprocess.run(
            [binary] + flags + [prompt_text],
            env=env,
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
        return {"response_text": "", "latency_ms": 60000, "exit_code": -1, "error": "timeout"}
    except FileNotFoundError:
        return {"response_text": "", "latency_ms": 0, "exit_code": -1, "error": f"{binary}: not found"}


def write_result(record: dict, run_id: str, results_dir: Optional[Path] = None) -> None:
    """Append a result record as a JSON line to results/<run_id>.jsonl."""
    out_dir = results_dir or RESULTS_DIR
    out_dir.mkdir(exist_ok=True)
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
    fixtures_dir: Optional[Path] = None,
    results_dir: Optional[Path] = None,
    claude_model: str = "claude-sonnet-4-6",
    gemini_model: str = "gemini-3-flash-preview",
) -> list[dict]:
    """Run all benchmark prompts for each provider in before/after conditions."""
    from tests.token_benchmark.benchmarks import BENCHMARKS, PROVIDER_CLI_CONFIG
    from tests.token_benchmark.scorer import score

    fdir = fixtures_dir or FIXTURES_DIR
    records = []

    with isolated_environments(fdir) as (empty_home, manifest_home):
        for provider in providers:
            for prompt in BENCHMARKS:
                for condition, home_dir in [("before", empty_home), ("after", manifest_home)]:
                    if provider in ("claude", "gemini"):
                        system_prompt = _read_system_prompt(home_dir, provider) if condition == "after" else ""
                        if provider == "claude":
                            api_result = await measure_api_claude(prompt.text, system_prompt, claude_model)
                            model_used = claude_model
                        else:
                            api_result = await measure_api_gemini(prompt.text, system_prompt, gemini_model)
                            model_used = gemini_model

                        quality = score(api_result.get("response_text") or "", prompt) if not api_result.get("error") else None
                        record = {
                            "run_id": run_id,
                            "provider": provider,
                            "model": model_used,
                            "condition": condition,
                            "category": prompt.category,
                            "prompt_id": prompt.prompt_id,
                            "input_tokens": api_result.get("input_tokens"),
                            "output_tokens": api_result.get("output_tokens"),
                            "quality_score": quality,
                            "response_text": (api_result.get("response_text") or "")[:200],
                            "latency_ms": api_result.get("latency_ms"),
                            "source": "api",
                            "error": api_result.get("error"),
                        }
                        write_result(record, run_id, results_dir)
                        records.append(record)
                        print(f"  [{provider}][api][{condition}][{prompt.prompt_id}] "
                              f"in={record['input_tokens']} out={record['output_tokens']} "
                              f"q={record['quality_score']}", flush=True)

                    if not api_only and provider in PROVIDER_CLI_CONFIG:
                        cli_config = PROVIDER_CLI_CONFIG[provider]
                        cli_result = measure_cli(prompt.text, cli_config, home_dir)
                        quality = score(cli_result.get("response_text") or "", prompt) if not cli_result.get("error") else None
                        record = {
                            "run_id": run_id,
                            "provider": provider,
                            "model": None,
                            "condition": condition,
                            "category": prompt.category,
                            "prompt_id": prompt.prompt_id,
                            "input_tokens": None,
                            "output_tokens": None,
                            "quality_score": quality,
                            "response_text": (cli_result.get("response_text") or "")[:200],
                            "latency_ms": cli_result.get("latency_ms"),
                            "source": "cli",
                            "error": cli_result.get("error"),
                        }
                        write_result(record, run_id, results_dir)
                        records.append(record)

    return records


def sync_fixtures(source_home: Optional[Path] = None, fixtures_dir: Optional[Path] = None) -> None:
    """Copy live manifest configs into fixtures/manifest/ snapshot."""
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

    agy_src = src / ".antigravity"
    if agy_src.exists():
        agy_dst = dst / ".antigravity"
        if agy_dst.exists():
            shutil.rmtree(agy_dst)
        shutil.copytree(agy_src, agy_dst)
        print("  synced .antigravity/")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Token benchmark harness")
    parser.add_argument("--providers", default="claude,gemini,antigravity")
    parser.add_argument("--api-only", action="store_true")
    parser.add_argument("--sync-fixtures", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--claude-model", default="claude-sonnet-4-6")
    parser.add_argument("--gemini-model", default="gemini-3-flash-preview")
    args = parser.parse_args()

    if args.sync_fixtures:
        print("Syncing fixtures from live home...")
        sync_fixtures()

    if not args.report_only:
        from datetime import datetime
        run_id = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        providers = [p.strip() for p in args.providers.split(",")]
        print(f"Running benchmark: providers={providers}, api_only={args.api_only}, run_id={run_id}")
        records = asyncio.run(run_benchmark(
            providers=providers,
            api_only=args.api_only,
            run_id=run_id,
            claude_model=args.claude_model,
            gemini_model=args.gemini_model,
        ))
        print(f"Done. {len(records)} records written to {RESULTS_DIR}/{run_id}.jsonl")

    print("Regenerating TOKEN_BENCHMARK.md...")
    sys.path.insert(0, str(REPO_ROOT))
    from tests.token_benchmark.reporter import update_report
    update_report(RESULTS_DIR, REPO_ROOT / "docs" / "TOKEN_BENCHMARK.md")
    print("Done.")
