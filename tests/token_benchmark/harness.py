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
