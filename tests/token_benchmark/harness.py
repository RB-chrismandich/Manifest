#!/usr/bin/env python3
"""Token benchmark harness: measures token overhead and quality before/after manifest."""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
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

# Rates mirror configs/claude/scripts/model_pricing.py (canonical $/MTok table);
# both Sonnet generations stay listed so --claude-model claude-sonnet-4-6 runs
# keep non-null cost_usd.
_SONNET_RATES: dict[str, float] = {
    "input": 3.00 / 1_000_000,
    "output": 15.00 / 1_000_000,
    "cache_write": 3.75 / 1_000_000,
    "cache_read": 0.30 / 1_000_000,
}

PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-5": _SONNET_RATES,
    "claude-sonnet-4-6": _SONNET_RATES,
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
    claude_model: str = "claude-sonnet-5",
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
    unsupported_warned: set[str] = set()

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
                        if provider not in unsupported_warned:
                            unsupported_warned.add(provider)
                            print(
                                f"  [{provider}][cli] unsupported: no "
                                "system-prompt injection strategy; recording "
                                "'unsupported' rows",
                                flush=True,
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


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_FIXTURE_PLACEHOLDER_HOME = "/Users/developer"


def _scrub_fixture_pii(text: str, home: Path) -> str:
    """Strip terminal escape codes and the contributor's real home/username
    from text before it lands in a tracked repo fixture (#552 follow-up).

    Fixtures under tests/token_benchmark/fixtures/ are committed and read by
    anyone who clones the repo, so a live CLAUDE.md or GEMINI.md synced via
    --sync-fixtures must not leak the operator's absolute home directory
    path, OS username, or raw ANSI/SGR escape sequences captured from their
    terminal.

    This scrubber intentionally does NOT redact secrets (e.g. API keys) — it
    only handles PII in the two files sync_fixtures() ever copies. The real
    secret-leak defense is sync_fixtures() never copying settings.json (or
    any other file with an `env` mapping) into the fixture tree at all; see
    its docstring.
    """
    text = _ANSI_ESCAPE_RE.sub("", text)
    home_str = str(home)
    if home_str and home_str in text:
        text = text.replace(home_str, _FIXTURE_PLACEHOLDER_HOME)
    username = home.name
    if username and username not in ("developer", ""):
        text = re.sub(rf"(?<![\w.-]){re.escape(username)}(?![\w.-])", "developer", text)
    return text


def _fixture_allowlist() -> list[str]:
    """Repo-relative paths sync_fixtures() may copy into the committed
    fixtures tree.

    Security (fixture tree is committed, read by anyone who clones the repo):
    only the files the benchmark actually reads at run time are ever synced.
    This set is derived from
    tests.token_benchmark.benchmarks.MANIFEST_SYSTEM_PROMPT_PATHS — the same
    mapping _read_system_prompt() uses — so the allowlist can never drift
    from what the harness consumes. ~/.claude/settings.json is deliberately
    excluded: nothing in this harness reads it, and it is a supported place
    for API keys under its `env` mapping, which _scrub_fixture_pii() does not
    redact. Do not add settings.json (or any other file) to this allowlist
    without also adding redaction for any value a user could plausibly put a
    secret in.
    """
    from tests.token_benchmark.benchmarks import MANIFEST_SYSTEM_PROMPT_PATHS

    # Preserve MANIFEST_SYSTEM_PROMPT_PATHS insertion order; drop the `None`
    # entry (antigravity has no system-prompt injection) and de-dupe.
    return list(dict.fromkeys(p for p in MANIFEST_SYSTEM_PROMPT_PATHS.values() if p))


def _write_compressed_fixture(fixtures_dir: Path, compression: int | None) -> None:
    """Write fixtures/../fixtures-compressed/.claude/CLAUDE.md truncated to
    the first `compression`% of lines. No-op when compression is None."""
    if compression is None:
        return
    claude_src = fixtures_dir / ".claude" / "CLAUDE.md"
    if not claude_src.exists():
        print(
            f"  skip compression: {claude_src} not found (run without --compression first to sync)"
        )
        return
    all_lines = claude_src.read_text().splitlines()
    keep = max(1, len(all_lines) * compression // 100)
    compressed_dst = (
        fixtures_dir.parent / "fixtures-compressed" / ".claude" / "CLAUDE.md"
    )
    compressed_dst.parent.mkdir(parents=True, exist_ok=True)
    compressed_dst.write_text("\n".join(all_lines[:keep]))
    print(f"  compressed fixture: {keep}/{len(all_lines)} lines → {compressed_dst}")


def sync_fixtures(
    source_home: Path | None = None,
    fixtures_dir: Path | None = None,
    compression: int | None = None,
) -> None:
    """Copy live manifest configs into fixtures/manifest/ snapshot.

    If compression is given (e.g. 50), also write a compressed fixture at
    fixtures/../fixtures-compressed/ containing the first compression% of lines
    from CLAUDE.md (see _write_compressed_fixture).

    Copied content is scrubbed (see _scrub_fixture_pii) so a --sync-fixtures
    run never reintroduces a contributor's real home path/username or stray
    ANSI escape codes into the tracked fixtures (#552).

    Which files get copied at all is governed by _fixture_allowlist() — see
    its docstring for the security rationale (settings.json is deliberately
    never synced).
    """
    src = source_home or Path.home()
    dst = fixtures_dir or FIXTURES_DIR

    for rel in _fixture_allowlist():
        source = src / rel
        dest = dst / rel
        if source.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            scrubbed = _scrub_fixture_pii(source.read_text(), src)
            dest.write_text(scrubbed)
            print(f"  synced {rel}")
        else:
            print(f"  skip {rel} (not found at {source})")

    # Antigravity has no system prompt injection (MANIFEST_SYSTEM_PROMPT_PATHS["antigravity"] = None)
    # so its IDE installation does not need to be snapshotted; the empty dir marker suffices.
    print("  skip .antigravity/ (no system prompt injection configured)")
    print(
        "  skip .claude/settings.json (not read by the benchmark; never "
        "synced by design — see sync_fixtures() docstring)"
    )

    _write_compressed_fixture(dst, compression)


def missing_api_sdks(providers: list[str]) -> list[str]:
    """Return the SDK packages required for the requested API providers but
    not importable in this environment (#547). Antigravity has no API path."""
    missing = []
    if "claude" in providers and not HAS_ANTHROPIC:
        missing.append("anthropic (claude API path)")
    if "gemini" in providers and not HAS_GENAI:
        missing.append("google-genai (gemini API path)")
    return missing


WORKFLOW_FIXTURES_DIR = Path(__file__).parent / "workflows" / "fixtures"
WORKFLOW_CONDITIONS = ("none", "slim", "full")
ACADEMIC_CONDITIONS = ("before", "after", "cached", "tiered", "compressed")
ACADEMIC_DEFAULT_CONDITIONS = ("before", "after")
WORKFLOW_DEFAULT_TIER = {"claude": "sonnet", "gemini": "flash"}


def _workflow_fixture_ids(root: Path) -> list[str]:
    """List the fixture ids declared in the frozen workflow manifest."""
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return sorted(manifest.get("workflows", {}))


def _validate_conditions(conditions, valid, label, parser) -> None:
    bad = [c for c in conditions if c not in valid]
    if bad:
        parser.error(
            f"Unknown {label} conditions: {', '.join(bad)}. Valid: {', '.join(valid)}"
        )


def _resolve_conditions(args, parser) -> tuple[list[str], list[str]]:
    """Resolve academic and workflow condition lists from --suite/--conditions.

    `--suite all` uses each suite's own default and rejects an explicit
    `--conditions` (ambiguous which suite it targets); a custom list requires
    a single selected suite.
    """
    if args.conditions is not None and args.suite == "all":
        parser.error(
            "--conditions is ambiguous for --suite all; select a single --suite"
        )
    requested = (
        [c.strip() for c in args.conditions.split(",") if c.strip()]
        if args.conditions is not None
        else None
    )
    academic = list(ACADEMIC_DEFAULT_CONDITIONS)
    workflow = list(WORKFLOW_CONDITIONS)
    if requested is not None and args.suite == "academic":
        _validate_conditions(requested, ACADEMIC_CONDITIONS, "academic", parser)
        academic = requested
    if requested is not None and args.suite == "workflow":
        _validate_conditions(requested, WORKFLOW_CONDITIONS, "workflow", parser)
        workflow = requested
    return academic, workflow


def _sdk_guard_providers(args, providers: list[str]) -> list[str]:
    """Providers this invocation will call through an SDK-backed adapter and
    must therefore have an importable SDK for, before any writes happen."""
    from tests.token_benchmark.workflows.transport import SUPPORTED_PROVIDERS

    if args.report_only:
        return []
    needed: set[str] = set()
    if args.suite in ("academic", "all") and not args.cli_only:
        needed.update(providers)
    if args.suite in ("workflow", "all"):
        needed.update(p for p in providers if p in SUPPORTED_PROVIDERS)
    return sorted(needed)


@dataclass(frozen=True)
class WorkflowRunSpec:
    """Settings for one `run_workflow()` invocation."""

    providers: list[str]
    conditions: list[str]
    run_id: str
    trials: int
    timeout_s: float
    fixture_image: str | None
    results_dir: Path | None = None
    fixtures_dir: Path | None = None


async def run_workflow(spec: WorkflowRunSpec) -> list[dict]:
    """Run the workflow suite for each requested supported provider and
    write each validated version-2 record to results/<run_id>.jsonl."""
    from tests.token_benchmark.workflows.evaluate import ContainerExecutor
    from tests.token_benchmark.workflows.runner import TrialContext, run_workflow_suite
    from tests.token_benchmark.workflows.transport import SUPPORTED_PROVIDERS
    from tests.token_benchmark.workflows.transport import invoke as workflow_invoke

    root = spec.fixtures_dir or WORKFLOW_FIXTURES_DIR
    fixture_ids = _workflow_fixture_ids(root)
    executor = ContainerExecutor(spec.fixture_image) if spec.fixture_image else None

    records: list[dict] = []
    for provider in spec.providers:
        if provider not in SUPPORTED_PROVIDERS or provider not in WORKFLOW_DEFAULT_TIER:
            continue
        config = TrialContext(
            invoke_fn=workflow_invoke,
            executor=executor,
            provider=provider,
            model=WORKFLOW_DEFAULT_TIER[provider],
            timeout_s=spec.timeout_s,
        )
        provider_records = await run_workflow_suite(
            root, fixture_ids, spec.conditions, spec.trials, config
        )
        for record in provider_records:
            record["run_id"] = spec.run_id
            write_result(record, spec.run_id, spec.results_dir)
            records.append(record)
    return records


def _build_arg_parser():
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
    parser.add_argument("--claude-model", default="claude-sonnet-5")
    parser.add_argument("--gemini-model", default="gemini-3-flash-preview")
    parser.add_argument(
        "--conditions",
        default=None,
        help=(
            "Comma-separated conditions for the selected --suite: "
            "before,after,cached,tiered,compressed (academic) or "
            "none,slim,full (workflow). Invalid for --suite all."
        ),
    )
    parser.add_argument(
        "--suite",
        choices=("academic", "workflow", "all"),
        default="workflow",
        help="Which benchmark suite(s) to run",
    )
    parser.add_argument(
        "--trials", type=int, default=3, help="Workflow suite repetitions"
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=120.0,
        help="Workflow suite per-call timeout",
    )
    parser.add_argument(
        "--fixture-image",
        default=None,
        help="Container image for workflow implementation-fixture execution",
    )
    return parser


def _run_selected_suites(
    args, providers, academic_conditions, workflow_conditions, run_id
) -> None:
    if args.suite in ("academic", "all"):
        mode = (
            "cli-only"
            if args.cli_only
            else ("api-only" if args.api_only else "api+cli")
        )
        print(
            f"Running academic benchmark: providers={providers}, mode={mode}, run_id={run_id}"
        )
        records = asyncio.run(
            run_benchmark(
                providers=providers,
                api_only=args.api_only,
                cli_only=args.cli_only,
                conditions=academic_conditions,
                run_id=run_id,
                claude_model=args.claude_model,
                gemini_model=args.gemini_model,
            )
        )
        print(
            f"Done. {len(records)} academic records written to {RESULTS_DIR}/{run_id}.jsonl"
        )
    if args.suite in ("workflow", "all"):
        print(
            f"Running workflow benchmark: providers={providers}, "
            f"conditions={workflow_conditions}, trials={args.trials}, run_id={run_id}"
        )
        spec = WorkflowRunSpec(
            providers=providers,
            conditions=workflow_conditions,
            run_id=run_id,
            trials=args.trials,
            timeout_s=args.timeout_seconds,
            fixture_image=args.fixture_image,
        )
        records = asyncio.run(run_workflow(spec))
        print(
            f"Done. {len(records)} workflow records written to {RESULTS_DIR}/{run_id}.jsonl"
        )


def main(argv: list[str] | None = None) -> None:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.trials <= 0:
        parser.error("--trials must be positive")
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    academic_conditions, workflow_conditions = _resolve_conditions(args, parser)

    # Hard-fail before any writes: an SDK-backed run without its SDK previously
    # "succeeded" in seconds while appending junk error rows (#547).
    missing = missing_api_sdks(_sdk_guard_providers(args, providers))
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
        _run_selected_suites(
            args, providers, academic_conditions, workflow_conditions, run_id
        )

    print("Regenerating TOKEN_BENCHMARK.md...")
    from tests.token_benchmark.reporter import update_report

    update_report(RESULTS_DIR, REPO_ROOT / "docs" / "TOKEN_BENCHMARK.md")
    print("Done.")


if __name__ == "__main__":
    main()
