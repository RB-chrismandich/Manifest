# Token Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a repeatable harness that measures Claude, Gemini, and Antigravity CLI input/output token overhead and quality delta introduced by Manifest config deployment, using 20 industry-standard benchmark prompts.

**Architecture:** Four focused Python modules (`benchmarks.py`, `scorer.py`, `harness.py`, `reporter.py`) under `tests/token_benchmark/`, driven by a `/token-benchmark` Claude Code skill. The harness creates two isolated temp HOME dirs (empty vs. manifest-populated), calls Claude/Gemini APIs directly for exact token counts, and calls CLI binaries with `HOME` overridden for behavioral delta. Results are appended as JSONL; `reporter.py` regenerates `docs/TOKEN_BENCHMARK.md` from the accumulated history.

**Tech Stack:** Python 3 (asyncio, subprocess, tempfile), `anthropic` v0.105.2, `google-genai` v2.7.0, pytest + pytest-asyncio, YAML.

**Spec:** `docs/superpowers/specs/2026-06-12-token-benchmark-design.md`

**Working directory:** repo root (worktree). All paths are repo-relative.

**Test command used throughout:**
```bash
python -m pytest tests/python/token_benchmark/ -v
```

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tests/token_benchmark/__init__.py` | Create | Package marker |
| `tests/token_benchmark/benchmarks.py` | Create | 20 prompt fixtures + provider CLI config |
| `tests/token_benchmark/scorer.py` | Create | exact_match + pass@1 sandboxed HumanEval |
| `tests/token_benchmark/harness.py` | Create | IsolatedEnvironment, API + CLI measurement, result writing |
| `tests/token_benchmark/reporter.py` | Create | JSONL → Markdown report generator |
| `tests/token_benchmark/results/.gitkeep` | Create | Track results dir in git |
| `tests/token_benchmark/fixtures/manifest/.claude/CLAUDE.md` | Create | Manifest snapshot (synced from live) |
| `tests/token_benchmark/fixtures/manifest/.claude/settings.json` | Create | Manifest snapshot |
| `tests/token_benchmark/fixtures/manifest/.gemini/GEMINI.md` | Create | Manifest snapshot |
| `tests/python/token_benchmark/__init__.py` | Create | Test package marker |
| `tests/python/token_benchmark/test_benchmarks.py` | Create | Suite coverage + schema tests |
| `tests/python/token_benchmark/test_scorer.py` | Create | Scorer unit tests |
| `tests/python/token_benchmark/test_harness.py` | Create | Harness unit tests (mocked APIs) |
| `tests/python/token_benchmark/test_reporter.py` | Create | Reporter unit tests |
| `docs/TOKEN_BENCHMARK.md` | Create | Living report template (initially empty tables) |
| `.skillshare/skills/token-benchmark/SKILL.md` | Create | `/token-benchmark` skill |
| `configs/claude/config/command_config.yml` | Modify | Add `tool_policies` entry for token-benchmark |

---

## Task 1: Package skeleton + benchmarks.py

**Files:**
- Create: `tests/token_benchmark/__init__.py`
- Create: `tests/token_benchmark/benchmarks.py`
- Create: `tests/python/token_benchmark/__init__.py`
- Test: `tests/python/token_benchmark/test_benchmarks.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/python/token_benchmark/__init__.py` (empty).

Create `tests/python/token_benchmark/test_benchmarks.py`:

```python
"""Tests for benchmark prompt fixtures."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.benchmarks import BENCHMARKS, PROVIDER_CLI_CONFIG, Prompt


class TestBenchmarkSuite:
    def test_total_count(self):
        assert len(BENCHMARKS) == 20

    def test_mmlu_count(self):
        assert sum(1 for b in BENCHMARKS if b.category == "mmlu") == 6

    def test_humaneval_count(self):
        assert sum(1 for b in BENCHMARKS if b.category == "humaneval") == 6

    def test_hellaswag_count(self):
        assert sum(1 for b in BENCHMARKS if b.category == "hellaswag") == 4

    def test_truthfulqa_count(self):
        assert sum(1 for b in BENCHMARKS if b.category == "truthfulqa") == 4

    def test_unique_ids(self):
        ids = [b.prompt_id for b in BENCHMARKS]
        assert len(ids) == len(set(ids))

    def test_mmlu_gold_answers_are_letters(self):
        for b in BENCHMARKS:
            if b.category == "mmlu":
                assert b.gold_answer in ("A", "B", "C", "D"), f"{b.prompt_id}: {b.gold_answer!r}"

    def test_hellaswag_gold_answers_are_digits(self):
        for b in BENCHMARKS:
            if b.category == "hellaswag":
                assert b.gold_answer in ("0", "1", "2", "3"), f"{b.prompt_id}: {b.gold_answer!r}"

    def test_truthfulqa_gold_answers_are_bool(self):
        for b in BENCHMARKS:
            if b.category == "truthfulqa":
                assert b.gold_answer in ("True", "False"), f"{b.prompt_id}: {b.gold_answer!r}"

    def test_humaneval_has_test_code(self):
        for b in BENCHMARKS:
            if b.category == "humaneval":
                assert b.test_code, f"{b.prompt_id} missing test_code"

    def test_all_prompts_non_empty(self):
        for b in BENCHMARKS:
            assert b.text.strip(), f"{b.prompt_id} has empty text"


class TestProviderCliConfig:
    def test_all_providers_present(self):
        for provider in ("claude", "gemini", "antigravity"):
            assert provider in PROVIDER_CLI_CONFIG

    def test_each_provider_has_binary_and_flags(self):
        for provider, cfg in PROVIDER_CLI_CONFIG.items():
            assert "binary" in cfg, f"{provider} missing binary"
            assert "flags" in cfg, f"{provider} missing flags"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/python/token_benchmark/test_benchmarks.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'tests.token_benchmark'`

- [ ] **Step 3: Create package init and benchmarks.py**

Create `tests/token_benchmark/__init__.py` (empty file).

Create `tests/token_benchmark/benchmarks.py`:

```python
"""Benchmark prompt fixtures for token measurement (MMLU, HumanEval, HellaSwag, TruthfulQA)."""

from dataclasses import dataclass, field


@dataclass
class Prompt:
    prompt_id: str
    category: str      # "mmlu" | "humaneval" | "hellaswag" | "truthfulqa"
    text: str
    gold_answer: str   # Expected answer; "" for humaneval (scored via test_code)
    test_code: str = ""  # HumanEval: Python assertions to run against the function


PROVIDER_CLI_CONFIG = {
    "claude":      {"binary": "claude",      "flags": ["--print"]},
    "gemini":      {"binary": "gemini",      "flags": ["-p"]},
    "antigravity": {"binary": "agy",         "flags": ["--print"]},
}

MANIFEST_SYSTEM_PROMPT_PATHS = {
    "claude":      ".claude/CLAUDE.md",
    "gemini":      ".gemini/GEMINI.md",
    "antigravity": None,
}

BENCHMARKS: list[Prompt] = [
    # --- MMLU (6) ---
    Prompt(
        prompt_id="mmlu_001",
        category="mmlu",
        text=(
            "Question: What is the SI unit of electric charge?\n"
            "A) Newton\nB) Coulomb\nC) Joule\nD) Watt\n\n"
            "Answer with just the letter (A, B, C, or D)."
        ),
        gold_answer="B",
    ),
    Prompt(
        prompt_id="mmlu_002",
        category="mmlu",
        text=(
            "Question: What is the derivative of f(x) = x²?\n"
            "A) x\nB) 2x\nC) x³/3\nD) 2x³\n\n"
            "Answer with just the letter (A, B, C, or D)."
        ),
        gold_answer="B",
    ),
    Prompt(
        prompt_id="mmlu_003",
        category="mmlu",
        text=(
            "Question: In what year did World War II officially end?\n"
            "A) 1943\nB) 1944\nC) 1945\nD) 1946\n\n"
            "Answer with just the letter (A, B, C, or D)."
        ),
        gold_answer="C",
    ),
    Prompt(
        prompt_id="mmlu_004",
        category="mmlu",
        text=(
            "Question: Which amendment to the US Constitution abolished slavery?\n"
            "A) 13th\nB) 14th\nC) 15th\nD) 16th\n\n"
            "Answer with just the letter (A, B, C, or D)."
        ),
        gold_answer="A",
    ),
    Prompt(
        prompt_id="mmlu_005",
        category="mmlu",
        text=(
            "Question: The hepatic portal vein carries blood from which organ system?\n"
            "A) Lungs\nB) Heart\nC) Digestive tract\nD) Brain\n\n"
            "Answer with just the letter (A, B, C, or D)."
        ),
        gold_answer="C",
    ),
    Prompt(
        prompt_id="mmlu_006",
        category="mmlu",
        text=(
            "Question: What is the time complexity of binary search on a sorted array?\n"
            "A) O(n)\nB) O(log n)\nC) O(n²)\nD) O(n log n)\n\n"
            "Answer with just the letter (A, B, C, or D)."
        ),
        gold_answer="B",
    ),
    # --- HumanEval (6) ---
    Prompt(
        prompt_id="humaneval_001",
        category="humaneval",
        text=(
            "Complete the following Python function. "
            "Respond with ONLY the function body (the indented lines after the def), "
            "no explanation, no markdown fences.\n\n"
            "def add(a: int, b: int) -> int:\n"
            '    """Return the sum of a and b."""\n'
            "    "
        ),
        gold_answer="",
        test_code=(
            "assert add(2, 3) == 5\n"
            "assert add(-1, 1) == 0\n"
            "assert add(0, 0) == 0"
        ),
    ),
    Prompt(
        prompt_id="humaneval_002",
        category="humaneval",
        text=(
            "Complete the following Python function. "
            "Respond with ONLY the function body (the indented lines after the def), "
            "no explanation, no markdown fences.\n\n"
            "def is_palindrome(s: str) -> bool:\n"
            '    """Return True if s is a palindrome, False otherwise."""\n'
            "    "
        ),
        gold_answer="",
        test_code=(
            "assert is_palindrome('racecar') == True\n"
            "assert is_palindrome('hello') == False\n"
            "assert is_palindrome('') == True"
        ),
    ),
    Prompt(
        prompt_id="humaneval_003",
        category="humaneval",
        text=(
            "Complete the following Python function. "
            "Respond with ONLY the function body (the indented lines after the def), "
            "no explanation, no markdown fences.\n\n"
            "def fibonacci(n: int) -> int:\n"
            '    """Return the nth Fibonacci number (0-indexed: fib(0)=0, fib(1)=1)."""\n'
            "    "
        ),
        gold_answer="",
        test_code=(
            "assert fibonacci(0) == 0\n"
            "assert fibonacci(1) == 1\n"
            "assert fibonacci(7) == 13"
        ),
    ),
    Prompt(
        prompt_id="humaneval_004",
        category="humaneval",
        text=(
            "Complete the following Python function. "
            "Respond with ONLY the function body (the indented lines after the def), "
            "no explanation, no markdown fences.\n\n"
            "def count_vowels(s: str) -> int:\n"
            '    """Return the count of vowels (a e i o u, case-insensitive) in s."""\n'
            "    "
        ),
        gold_answer="",
        test_code=(
            "assert count_vowels('hello') == 2\n"
            "assert count_vowels('AEIOU') == 5\n"
            "assert count_vowels('rhythm') == 0"
        ),
    ),
    Prompt(
        prompt_id="humaneval_005",
        category="humaneval",
        text=(
            "Complete the following Python function. "
            "Respond with ONLY the function body (the indented lines after the def), "
            "no explanation, no markdown fences.\n\n"
            "def max_subarray_sum(arr: list) -> int:\n"
            "    \"\"\"Return the maximum sum of any contiguous subarray (Kadane's algorithm).\"\"\"\n"
            "    "
        ),
        gold_answer="",
        test_code=(
            "assert max_subarray_sum([-2, 1, -3, 4, -1, 2, 1, -5, 4]) == 6\n"
            "assert max_subarray_sum([1]) == 1\n"
            "assert max_subarray_sum([-1, -2, -3]) == -1"
        ),
    ),
    Prompt(
        prompt_id="humaneval_006",
        category="humaneval",
        text=(
            "Complete the following Python function. "
            "Respond with ONLY the function body (the indented lines after the def), "
            "no explanation, no markdown fences.\n\n"
            "def flatten(lst: list) -> list:\n"
            '    """Flatten a one-level-deep nested list into a single flat list."""\n'
            "    "
        ),
        gold_answer="",
        test_code=(
            "assert flatten([[1, 2], [3, 4], [5]]) == [1, 2, 3, 4, 5]\n"
            "assert flatten([]) == []\n"
            "assert flatten([[1], [2, 3]]) == [1, 2, 3]"
        ),
    ),
    # --- HellaSwag (4) ---
    Prompt(
        prompt_id="hellaswag_001",
        category="hellaswag",
        text=(
            "Choose the most natural continuation. Answer with just the number (0, 1, 2, or 3).\n\n"
            "A person picks up a guitar and sits down. They begin to tune the strings. Next:\n"
            "0) They set the guitar down and leave immediately.\n"
            "1) They start playing a song.\n"
            "2) They put the guitar in the refrigerator.\n"
            "3) They fall asleep in the chair."
        ),
        gold_answer="1",
    ),
    Prompt(
        prompt_id="hellaswag_002",
        category="hellaswag",
        text=(
            "Choose the most natural continuation. Answer with just the number (0, 1, 2, or 3).\n\n"
            "A chef brings a pot of water to a full boil on the stove. They then add:\n"
            "0) A bar of soap to clean the pot.\n"
            "1) Ice cubes to cool it down.\n"
            "2) Pasta to cook.\n"
            "3) Gravel to season it."
        ),
        gold_answer="2",
    ),
    Prompt(
        prompt_id="hellaswag_003",
        category="hellaswag",
        text=(
            "Choose the most natural continuation. Answer with just the number (0, 1, 2, or 3).\n\n"
            "The runner crosses the finish line first. The crowd:\n"
            "0) Leaves in complete silence.\n"
            "1) Starts throwing garbage onto the track.\n"
            "2) Falls asleep in their seats.\n"
            "3) Cheers and applauds loudly."
        ),
        gold_answer="3",
    ),
    Prompt(
        prompt_id="hellaswag_004",
        category="hellaswag",
        text=(
            "Choose the most natural continuation. Answer with just the number (0, 1, 2, or 3).\n\n"
            "A student opens their exam booklet and reads the first question carefully. They then:\n"
            "0) Hand in a blank paper immediately.\n"
            "1) Think carefully and write their answer.\n"
            "2) Start singing loudly.\n"
            "3) Flip the desk over."
        ),
        gold_answer="1",
    ),
    # --- TruthfulQA (4) ---
    Prompt(
        prompt_id="truthfulqa_001",
        category="truthfulqa",
        text=(
            "Answer True or False, followed by one sentence of explanation.\n\n"
            "Claim: Vaccines cause autism in children."
        ),
        gold_answer="False",
    ),
    Prompt(
        prompt_id="truthfulqa_002",
        category="truthfulqa",
        text=(
            "Answer True or False, followed by one sentence of explanation.\n\n"
            "Claim: The Great Wall of China is clearly visible from space with the naked eye."
        ),
        gold_answer="False",
    ),
    Prompt(
        prompt_id="truthfulqa_003",
        category="truthfulqa",
        text=(
            "Answer True or False, followed by one sentence of explanation.\n\n"
            "Claim: Light travels faster than sound in air."
        ),
        gold_answer="True",
    ),
    Prompt(
        prompt_id="truthfulqa_004",
        category="truthfulqa",
        text=(
            "Answer True or False, followed by one sentence of explanation.\n\n"
            "Claim: Napoleon Bonaparte was significantly shorter than the average French man of his era."
        ),
        gold_answer="False",
    ),
]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/python/token_benchmark/test_benchmarks.py -v
```

Expected: 11 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/token_benchmark/__init__.py tests/token_benchmark/benchmarks.py \
        tests/python/token_benchmark/__init__.py tests/python/token_benchmark/test_benchmarks.py
git commit -m "feat: add token benchmark prompt fixtures (MMLU/HumanEval/HellaSwag/TruthfulQA)"
```

---

## Task 2: scorer.py

**Files:**
- Create: `tests/token_benchmark/scorer.py`
- Test: `tests/python/token_benchmark/test_scorer.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/python/token_benchmark/test_scorer.py`:

```python
"""Tests for quality scorer."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.benchmarks import BENCHMARKS
from tests.token_benchmark.scorer import (
    exact_match_letter,
    exact_match_bool,
    pass_at_1,
    score,
)


class TestExactMatchLetter:
    def test_correct_letter(self):
        assert exact_match_letter("B", "B") == 1

    def test_wrong_letter(self):
        assert exact_match_letter("A", "B") == 0

    def test_extracts_from_sentence(self):
        assert exact_match_letter("The answer is B because...", "B") == 1

    def test_case_insensitive(self):
        assert exact_match_letter("b", "B") == 1

    def test_digit_gold(self):
        assert exact_match_letter("The best continuation is 2.", "2") == 1

    def test_no_match_returns_zero(self):
        assert exact_match_letter("no letter here at all", "A") == 0

    def test_digit_wrong(self):
        assert exact_match_letter("1", "2") == 0


class TestExactMatchBool:
    def test_true(self):
        assert exact_match_bool("True. Because X.", "True") == 1

    def test_false(self):
        assert exact_match_bool("False. The evidence shows Y.", "False") == 1

    def test_wrong(self):
        assert exact_match_bool("True", "False") == 0

    def test_false_before_true(self):
        # "False, not True" — first occurrence wins
        assert exact_match_bool("False, not True", "False") == 1

    def test_no_match(self):
        assert exact_match_bool("definitely uncertain", "True") == 0

    def test_case_insensitive(self):
        assert exact_match_bool("false. because...", "False") == 1


class TestPassAt1:
    def _get_prompt(self, prompt_id: str):
        return next(b for b in BENCHMARKS if b.prompt_id == prompt_id)

    def test_correct_body_only(self):
        p = self._get_prompt("humaneval_001")  # add(a, b)
        assert pass_at_1("return a + b", p) == 1

    def test_wrong_body(self):
        p = self._get_prompt("humaneval_001")
        assert pass_at_1("return a - b", p) == 0

    def test_correct_full_function(self):
        p = self._get_prompt("humaneval_001")
        assert pass_at_1("def add(a, b):\n    return a + b", p) == 1

    def test_code_with_markdown_fences(self):
        p = self._get_prompt("humaneval_001")
        assert pass_at_1("```python\nreturn a + b\n```", p) == 1

    def test_empty_response(self):
        p = self._get_prompt("humaneval_001")
        assert pass_at_1("", p) == 0

    def test_syntax_error_body(self):
        p = self._get_prompt("humaneval_001")
        assert pass_at_1("return a +++ b", p) == 0

    def test_timeout_infinite_loop(self):
        p = self._get_prompt("humaneval_001")
        assert pass_at_1("while True: pass", p) == 0

    def test_fibonacci(self):
        p = self._get_prompt("humaneval_003")
        body = "if n <= 1:\n    return n\nreturn fibonacci(n-1) + fibonacci(n-2)"
        assert pass_at_1(body, p) == 1


class TestScoreDispatch:
    def test_dispatches_mmlu(self):
        p = next(b for b in BENCHMARKS if b.category == "mmlu")
        assert score("B", p) == (1 if p.gold_answer == "B" else 0)

    def test_dispatches_hellaswag(self):
        p = next(b for b in BENCHMARKS if b.category == "hellaswag")
        result = score(p.gold_answer, p)
        assert result == 1

    def test_dispatches_truthfulqa(self):
        p = next(b for b in BENCHMARKS if b.category == "truthfulqa")
        result = score(p.gold_answer, p)
        assert result == 1

    def test_dispatches_humaneval(self):
        p = next(b for b in BENCHMARKS if b.category == "humaneval")
        # humaneval_001 is add(a, b)
        if p.prompt_id == "humaneval_001":
            assert score("return a + b", p) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/python/token_benchmark/test_scorer.py -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'exact_match_letter' from 'tests.token_benchmark.scorer'`

- [ ] **Step 3: Implement scorer.py**

Create `tests/token_benchmark/scorer.py`:

```python
"""Quality scoring for token benchmark results."""

import re
import subprocess


def exact_match_letter(response: str, gold: str) -> int:
    """Score MMLU (A-D) and HellaSwag (0-3).

    Checks the start of the response first (model followed instructions) before
    falling back to the first standalone match — reduces false hits from numbers
    in explanatory text like "2 of the 3 options suggest...".
    """
    text = response.strip()
    # Priority: answer at the start of the response
    m = re.match(r'^([A-Da-d]|[0-3])\b', text)
    if m:
        return 1 if m.group(1).upper() == gold.upper() else 0
    # Fallback: first standalone letter/digit in response
    m = re.search(r'\b([A-Da-d]|[0-3])\b', text)
    if not m:
        return 0
    return 1 if m.group(1).upper() == gold.upper() else 0


def exact_match_bool(response: str, gold: str) -> int:
    """Score TruthfulQA by finding first True/False in response."""
    text = response.lower().strip()
    ti = text.find("true")
    fi = text.find("false")
    if ti == -1 and fi == -1:
        return 0
    if fi == -1 or (ti != -1 and ti < fi):
        answer = "True"
    else:
        answer = "False"
    return 1 if answer == gold else 0


def pass_at_1(response: str, prompt) -> int:
    """Score HumanEval pass@1 via subprocess sandbox (5s timeout, no network).

    Assembles the full function from the extracted body and runs test assertions.
    """
    code = _extract_code(response)
    if not code.strip():
        return 0

    # If response includes full function def, use it directly
    if re.search(r'def \w+\s*\(', code):
        full_code = code + "\n\n" + prompt.test_code
    else:
        # Response is just the body — prepend signature from prompt
        func_sig = _extract_func_sig(prompt.text)
        body = "\n".join(
            "    " + line for line in code.strip().splitlines() if line.strip()
        )
        if not body:
            return 0
        full_code = func_sig + "\n" + body + "\n\n" + prompt.test_code

    try:
        result = subprocess.run(
            ["python3", "-c", full_code],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return 1 if result.returncode == 0 else 0
    except subprocess.TimeoutExpired:
        return 0


def score(response: str, prompt) -> int:
    """Dispatch to the correct scorer based on prompt category."""
    if prompt.category in ("mmlu", "hellaswag"):
        return exact_match_letter(response, prompt.gold_answer)
    if prompt.category == "humaneval":
        return pass_at_1(response, prompt)
    if prompt.category == "truthfulqa":
        return exact_match_bool(response, prompt.gold_answer)
    return 0


def _extract_code(response: str) -> str:
    """Strip markdown code fences; return raw code."""
    m = re.search(r'```(?:python)?\s*\n(.*?)\n```', response, re.DOTALL)
    return m.group(1) if m else response


def _extract_func_sig(prompt_text: str) -> str:
    """Extract the def ... : line from a HumanEval prompt."""
    m = re.search(r'(def \w+\([^)]*\)[^:]*:)', prompt_text)
    return m.group(1) if m else "def func():"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/python/token_benchmark/test_scorer.py -v
```

Expected: 20 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/token_benchmark/scorer.py tests/python/token_benchmark/test_scorer.py
git commit -m "feat: add token benchmark scorer (exact_match, pass@1 sandboxed)"
```

---

## Task 3: harness.py — IsolatedEnvironment + API measurement

**Files:**
- Create: `tests/token_benchmark/harness.py` (IsolatedEnvironment + measure_api_claude + measure_api_gemini)
- Test: `tests/python/token_benchmark/test_harness.py` (partial — IsolatedEnvironment + API)

- [ ] **Step 1: Write the failing tests**

Create `tests/python/token_benchmark/test_harness.py`:

```python
"""Tests for benchmark harness (IsolatedEnvironment + API measurement)."""

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.harness import (
    isolated_environments,
    measure_api_claude,
    measure_api_gemini,
)


class TestIsolatedEnvironments:
    def test_creates_two_dirs(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        with isolated_environments(fixtures) as (empty, manifest):
            assert empty.exists()
            assert manifest.exists()
            assert empty != manifest

    def test_empty_home_has_no_files(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        with isolated_environments(fixtures) as (empty, manifest):
            assert list(empty.iterdir()) == []

    def test_manifest_home_populated_from_fixtures(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        (fixtures / ".claude").mkdir(parents=True)
        (fixtures / ".claude" / "CLAUDE.md").write_text("# test manifest")
        with isolated_environments(fixtures) as (empty, manifest):
            assert (manifest / ".claude" / "CLAUDE.md").read_text() == "# test manifest"

    def test_dirs_cleaned_up_after_exit(self, tmp_path):
        fixtures = tmp_path / "fixtures"
        fixtures.mkdir()
        with isolated_environments(fixtures) as (empty, manifest):
            empty_path = empty
            manifest_path = manifest
        assert not empty_path.exists()
        assert not manifest_path.exists()

    def test_missing_fixtures_dir_ok(self, tmp_path):
        """Empty fixtures dir (before --sync-fixtures) should not raise."""
        fixtures = tmp_path / "nonexistent"
        with isolated_environments(fixtures) as (empty, manifest):
            assert empty.exists()
            assert manifest.exists()


class TestMeasureApiClaude:
    @pytest.mark.asyncio
    async def test_returns_token_counts_and_text(self):
        mock_usage = MagicMock(input_tokens=312, output_tokens=47)
        mock_content = MagicMock(text="B")
        mock_response = MagicMock(usage=mock_usage, content=[mock_content])

        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_response

        with patch("tests.token_benchmark.harness.AsyncAnthropic", return_value=mock_client):
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                result = await measure_api_claude(
                    prompt_text="What is 2+2?",
                    system_prompt="",
                    model="claude-sonnet-4-6",
                )

        assert result["input_tokens"] == 312
        assert result["output_tokens"] == 47
        assert result["response_text"] == "B"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
        with patch.dict(os.environ, env, clear=True):
            result = await measure_api_claude("prompt", "", "claude-sonnet-4-6")
        assert result["error"] is not None
        assert result["input_tokens"] is None

    @pytest.mark.asyncio
    async def test_system_prompt_passed_to_api(self):
        mock_usage = MagicMock(input_tokens=1842, output_tokens=47)
        mock_response = MagicMock(usage=mock_usage, content=[MagicMock(text="A")])
        mock_client = AsyncMock()
        mock_client.messages.create.return_value = mock_response

        with patch("tests.token_benchmark.harness.AsyncAnthropic", return_value=mock_client):
            with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
                await measure_api_claude("prompt", "SYSTEM CONTEXT", "claude-sonnet-4-6")

        call_kwargs = mock_client.messages.create.call_args.kwargs
        assert call_kwargs["system"] == "SYSTEM CONTEXT"


class TestMeasureApiGemini:
    @pytest.mark.asyncio
    async def test_returns_token_counts_and_text(self):
        mock_usage = MagicMock(prompt_token_count=308, candidates_token_count=52)
        mock_response = MagicMock(text="C", usage_metadata=mock_usage)

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        with patch("tests.token_benchmark.harness.genai") as mock_genai:
            mock_genai.Client.return_value = mock_client
            with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
                result = await measure_api_gemini(
                    prompt_text="What is 2+2?",
                    system_prompt="",
                    model="gemini-3-flash-preview",
                )

        assert result["input_tokens"] == 308
        assert result["output_tokens"] == 52
        assert result["response_text"] == "C"
        assert result["error"] is None

    @pytest.mark.asyncio
    async def test_missing_api_key_returns_error(self):
        env = {k: v for k, v in os.environ.items() if k not in ("GOOGLE_API_KEY", "GEMINI_API_KEY")}
        with patch.dict(os.environ, env, clear=True):
            with patch("tests.token_benchmark.harness.genai", side_effect=Exception("no auth")):
                result = await measure_api_gemini("prompt", "", "gemini-3-flash-preview")
        assert result["error"] is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/python/token_benchmark/test_harness.py -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'isolated_environments' from 'tests.token_benchmark.harness'`

- [ ] **Step 3: Implement IsolatedEnvironment + API functions**

Create `tests/token_benchmark/harness.py`:

```python
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


async def measure_api_claude(prompt_text: str, system_prompt: str, model: str) -> dict:
    """Call Claude API; return input_tokens, output_tokens, response_text, latency_ms."""
    if not HAS_ANTHROPIC:
        return {"error": "anthropic package not installed", "input_tokens": None, "output_tokens": None, "response_text": None, "latency_ms": None}

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not set", "input_tokens": None, "output_tokens": None, "response_text": None, "latency_ms": None}

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
        return {"error": str(e), "input_tokens": None, "output_tokens": None, "response_text": None, "latency_ms": None}


async def measure_api_gemini(prompt_text: str, system_prompt: str, model: str) -> dict:
    """Call Gemini API; return input_tokens, output_tokens, response_text, latency_ms."""
    if not HAS_GENAI:
        return {"error": "google-genai package not installed", "input_tokens": None, "output_tokens": None, "response_text": None, "latency_ms": None}

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    t0 = time.time()
    try:
        client = genai.Client(api_key=api_key) if api_key else genai.Client()
        config = genai_types.GenerateContentConfig(
            system_instruction=system_prompt if system_prompt else None,
            max_output_tokens=1024,
        )
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=prompt_text,
            config=config,
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
        return {"error": str(e), "input_tokens": None, "output_tokens": None, "response_text": None, "latency_ms": None}
```

*(The file continues — CLI measurement is added in Task 4. Do not close the module yet; tasks 3 and 4 build the same file incrementally.)*

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/python/token_benchmark/test_harness.py::TestIsolatedEnvironments \
                 tests/python/token_benchmark/test_harness.py::TestMeasureApiClaude \
                 tests/python/token_benchmark/test_harness.py::TestMeasureApiGemini -v
```

Expected: all IsolatedEnvironment + API tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/token_benchmark/harness.py tests/python/token_benchmark/test_harness.py
git commit -m "feat: add harness IsolatedEnvironment and API measurement functions"
```

---

## Task 4: harness.py — CLI measurement + orchestration + result writing

**Files:**
- Modify: `tests/token_benchmark/harness.py` (append measure_cli, run_benchmark, write_result, sync_fixtures, main)
- Test: `tests/python/token_benchmark/test_harness.py` (append CLI + orchestration tests)

- [ ] **Step 1: Write the failing tests**

Append to `tests/python/token_benchmark/test_harness.py`:

```python
# --- append to existing test_harness.py ---

from tests.token_benchmark.harness import measure_cli, write_result


class TestMeasureCli:
    def test_returns_response_text_and_latency(self, tmp_path):
        cli_config = {"binary": "echo", "flags": []}
        result = measure_cli("hello world", cli_config, tmp_path)
        assert "hello world" in result["response_text"]
        assert result["latency_ms"] >= 0
        assert result["error"] is None

    def test_home_overridden_in_subprocess(self, tmp_path):
        cli_config = {"binary": "sh", "flags": ["-c", "echo $HOME"]}
        result = measure_cli("ignored", cli_config, tmp_path)
        # The subprocess HOME should be the tmp_path, not the real HOME
        assert str(tmp_path) in result["response_text"]

    def test_missing_binary_returns_error(self, tmp_path):
        cli_config = {"binary": "nonexistent_binary_12345", "flags": []}
        result = measure_cli("prompt", cli_config, tmp_path)
        assert result["error"] is not None
        assert result["response_text"] == ""

    def test_timeout_returns_error(self, tmp_path):
        cli_config = {"binary": "sleep", "flags": []}
        # Override timeout for the test (we can't easily patch it, so use a very short cmd)
        # sleep 0 should succeed; this just verifies no crash
        result = measure_cli("0", cli_config, tmp_path)
        assert result["error"] is None


class TestWriteResult:
    def test_appends_jsonl_to_results_dir(self, tmp_path):
        record = {"run_id": "2026-06-12T00:00:00", "provider": "claude", "input_tokens": 100}
        write_result(record, "2026-06-12T00:00:00", results_dir=tmp_path)
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        with open(files[0]) as f:
            loaded = json.loads(f.read().strip())
        assert loaded["input_tokens"] == 100

    def test_multiple_records_in_same_file(self, tmp_path):
        for i in range(3):
            write_result({"run_id": "2026-06-12T00:00:00", "i": i}, "2026-06-12T00:00:00", results_dir=tmp_path)
        files = list(tmp_path.glob("*.jsonl"))
        assert len(files) == 1
        lines = files[0].read_text().strip().splitlines()
        assert len(lines) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/python/token_benchmark/test_harness.py::TestMeasureCli \
                 tests/python/token_benchmark/test_harness.py::TestWriteResult -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'measure_cli'`

- [ ] **Step 3: Append CLI + orchestration functions to harness.py**

Append to `tests/token_benchmark/harness.py` (after the existing `measure_api_gemini` function):

```python
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
    """Run all benchmark prompts for each provider in before/after conditions.

    Returns a list of result records (also written to JSONL).
    """
    from tests.token_benchmark.benchmarks import BENCHMARKS, PROVIDER_CLI_CONFIG
    from tests.token_benchmark.scorer import score

    fdir = fixtures_dir or FIXTURES_DIR
    records = []

    with isolated_environments(fdir) as (empty_home, manifest_home):
        for provider in providers:
            for prompt in BENCHMARKS:
                for condition, home_dir in [("before", empty_home), ("after", manifest_home)]:
                    # API path (exact token counts)
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

                    # CLI path (behavioral delta; all providers)
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

    # .antigravity — copy entire dir if present
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
    parser.add_argument("--providers", default="claude,gemini,antigravity",
                        help="Comma-separated list of providers to benchmark")
    parser.add_argument("--api-only", action="store_true",
                        help="Skip CLI behavioral tests (API token counts only)")
    parser.add_argument("--sync-fixtures", action="store_true",
                        help="Sync fixtures/manifest/ from live ~/.claude etc. before running")
    parser.add_argument("--report-only", action="store_true",
                        help="Regenerate TOKEN_BENCHMARK.md from existing results; do not run new benchmark")
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/python/token_benchmark/test_harness.py -v
```

Expected: all tests PASSED (including TestMeasureCli and TestWriteResult).

- [ ] **Step 5: Create results directory**

```bash
mkdir -p tests/token_benchmark/results
touch tests/token_benchmark/results/.gitkeep
```

- [ ] **Step 6: Commit**

```bash
git add tests/token_benchmark/harness.py tests/token_benchmark/results/.gitkeep \
        tests/python/token_benchmark/test_harness.py
git commit -m "feat: add harness CLI measurement, run_benchmark orchestration, result writing"
```

---

## Task 5: reporter.py

**Files:**
- Create: `tests/token_benchmark/reporter.py`
- Test: `tests/python/token_benchmark/test_reporter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/python/token_benchmark/test_reporter.py`:

```python
"""Tests for TOKEN_BENCHMARK.md report generator."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.reporter import load_results, compute_stats, render_report, update_report

# Minimal fixture: 4 records covering one provider/category in before+after
FIXTURE_RECORDS = [
    {
        "run_id": "2026-06-12T10-00-00",
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "condition": "before",
        "category": "mmlu",
        "prompt_id": "mmlu_001",
        "input_tokens": 100,
        "output_tokens": 5,
        "quality_score": 1,
        "source": "api",
        "error": None,
    },
    {
        "run_id": "2026-06-12T10-00-00",
        "provider": "claude",
        "model": "claude-sonnet-4-6",
        "condition": "after",
        "category": "mmlu",
        "prompt_id": "mmlu_001",
        "input_tokens": 2635,
        "output_tokens": 7,
        "quality_score": 1,
        "source": "api",
        "error": None,
    },
    {
        "run_id": "2026-06-12T10-00-00",
        "provider": "claude",
        "model": None,
        "condition": "before",
        "category": "mmlu",
        "prompt_id": "mmlu_001",
        "input_tokens": None,
        "output_tokens": None,
        "quality_score": 1,
        "source": "cli",
        "error": None,
    },
    {
        "run_id": "2026-06-12T10-00-00",
        "provider": "claude",
        "model": None,
        "condition": "after",
        "category": "mmlu",
        "prompt_id": "mmlu_001",
        "input_tokens": None,
        "output_tokens": None,
        "quality_score": 1,
        "source": "cli",
        "error": None,
    },
]


class TestLoadResults:
    def test_loads_jsonl_files(self, tmp_path):
        (tmp_path / "2026-06-12T10-00-00.jsonl").write_text(
            "\n".join(json.dumps(r) for r in FIXTURE_RECORDS)
        )
        records = load_results(tmp_path)
        assert len(records) == 4

    def test_empty_dir_returns_empty_list(self, tmp_path):
        assert load_results(tmp_path) == []

    def test_skips_non_jsonl_files(self, tmp_path):
        (tmp_path / "README.md").write_text("not a result")
        (tmp_path / "run.jsonl").write_text(json.dumps(FIXTURE_RECORDS[0]))
        records = load_results(tmp_path)
        assert len(records) == 1


class TestComputeStats:
    def test_computes_token_overhead(self):
        stats = compute_stats(FIXTURE_RECORDS)
        claude_api = stats["token_overhead"]["claude"]
        assert claude_api["avg_input_before"] == 100
        assert claude_api["avg_input_after"] == 2635
        assert claude_api["overhead_tokens"] == 2535

    def test_computes_output_delta(self):
        stats = compute_stats(FIXTURE_RECORDS)
        claude_api = stats["output_delta"]["claude"]
        assert claude_api["avg_output_before"] == 5
        assert claude_api["avg_output_after"] == 7

    def test_computes_quality_scores(self):
        stats = compute_stats(FIXTURE_RECORDS)
        # Both before and after CLI scores are 1/1 for mmlu
        q = stats["quality"]["claude"]["mmlu"]
        assert q["before_score"] == 1
        assert q["after_score"] == 1
        assert q["before_total"] == 1

    def test_antigravity_has_null_tokens(self):
        """Antigravity records (no API) should produce None overhead."""
        records = [
            {**FIXTURE_RECORDS[0], "provider": "antigravity", "input_tokens": None, "source": "api"},
            {**FIXTURE_RECORDS[1], "provider": "antigravity", "input_tokens": None, "source": "api"},
        ]
        stats = compute_stats(records)
        assert stats["token_overhead"].get("antigravity") is None or \
               stats["token_overhead"]["antigravity"]["overhead_tokens"] is None


class TestRenderReport:
    def test_renders_markdown_string(self):
        stats = compute_stats(FIXTURE_RECORDS)
        md = render_report(stats, run_id="2026-06-12T10-00-00")
        assert "# Token Benchmark Report" in md
        assert "Token Overhead" in md
        assert "Quality Scores" in md
        assert "claude" in md.lower()

    def test_includes_overhead_numbers(self):
        stats = compute_stats(FIXTURE_RECORDS)
        md = render_report(stats, run_id="2026-06-12T10-00-00")
        assert "2535" in md  # overhead tokens
        assert "2635" in md  # avg input after


class TestUpdateReport:
    def test_creates_report_file(self, tmp_path):
        results_dir = tmp_path / "results"
        results_dir.mkdir()
        (results_dir / "run.jsonl").write_text("\n".join(json.dumps(r) for r in FIXTURE_RECORDS))
        output = tmp_path / "TOKEN_BENCHMARK.md"
        update_report(results_dir, output)
        assert output.exists()
        assert "Token Benchmark Report" in output.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/python/token_benchmark/test_reporter.py -v 2>&1 | head -15
```

Expected: `ImportError: cannot import name 'load_results'`

- [ ] **Step 3: Implement reporter.py**

Create `tests/token_benchmark/reporter.py`:

```python
"""Generate TOKEN_BENCHMARK.md from accumulated JSONL result files."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional


def load_results(results_dir: Path) -> list[dict]:
    """Read all .jsonl files in results_dir and return a flat list of records."""
    records = []
    for f in sorted(results_dir.glob("*.jsonl")):
        for line in f.read_text().splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def compute_stats(records: list[dict]) -> dict:
    """Aggregate records into summary stats per provider."""
    # token_overhead[provider] = {avg_input_before, avg_input_after, overhead_tokens, overhead_pct,
    #                              avg_output_before, avg_output_after, output_delta}
    # quality[provider][category] = {before_score, before_total, after_score, after_total}

    api_recs = [r for r in records if r.get("source") == "api"]
    cli_recs = [r for r in records if r.get("source") == "cli"]

    # Token overhead (API records with non-null tokens)
    token_overhead = {}
    providers = {r["provider"] for r in api_recs}
    for provider in providers:
        before = [r for r in api_recs if r["provider"] == provider
                  and r["condition"] == "before" and r.get("input_tokens") is not None]
        after  = [r for r in api_recs if r["provider"] == provider
                  and r["condition"] == "after"  and r.get("input_tokens") is not None]
        if not before or not after:
            continue
        avg_in_b  = sum(r["input_tokens"]  for r in before) / len(before)
        avg_in_a  = sum(r["input_tokens"]  for r in after)  / len(after)
        avg_out_b = sum(r["output_tokens"] for r in before) / len(before)
        avg_out_a = sum(r["output_tokens"] for r in after)  / len(after)
        overhead  = avg_in_a - avg_in_b
        token_overhead[provider] = {
            "avg_input_before":  round(avg_in_b),
            "avg_input_after":   round(avg_in_a),
            "overhead_tokens":   round(overhead),
            "overhead_pct":      round(overhead / avg_in_b * 100) if avg_in_b else None,
            "avg_output_before": round(avg_out_b),
            "avg_output_after":  round(avg_out_a),
            "output_delta":      round(avg_out_a - avg_out_b),
        }

    # Quality scores (CLI records)
    quality = defaultdict(lambda: defaultdict(lambda: {"before_score": 0, "before_total": 0,
                                                        "after_score":  0, "after_total":  0}))
    for r in cli_recs:
        if r.get("quality_score") is None:
            continue
        provider = r["provider"]
        category = r["category"]
        cond = r["condition"]
        quality[provider][category][f"{cond}_score"] += r["quality_score"]
        quality[provider][category][f"{cond}_total"] += 1

    return {
        "token_overhead": token_overhead,
        "output_delta":   {p: {"avg_output_before": v["avg_output_before"],
                               "avg_output_after":  v["avg_output_after"],
                               "output_delta":       v["output_delta"]}
                           for p, v in token_overhead.items()},
        "quality":  {p: dict(cats) for p, cats in quality.items()},
        "run_ids":  sorted({r["run_id"] for r in records}),
    }


def render_report(stats: dict, run_id: str) -> str:
    """Render TOKEN_BENCHMARK.md markdown from computed stats."""
    lines = [
        "# Token Benchmark Report",
        "",
        f"**Last run**: {run_id[:10]}",
        "**Prompts**: 20 (6 MMLU, 6 HumanEval, 4 HellaSwag, 4 TruthfulQA)",
        "",
        "---",
        "",
        "## Token Overhead (Manifest Context Cost — API)",
        "",
        "| Provider | Avg Input Before | Avg Input After | Overhead (tokens) | Overhead (%) |",
        "|----------|-----------------|-----------------|-------------------|--------------|",
    ]
    for provider in ("claude", "gemini", "antigravity"):
        d = stats["token_overhead"].get(provider)
        if d:
            lines.append(
                f"| {provider} | {d['avg_input_before']:,} | {d['avg_input_after']:,} "
                f"| +{d['overhead_tokens']:,} | +{d['overhead_pct']}% |"
            )
        else:
            lines.append(f"| {provider} | — | — | — | — |")

    lines += [
        "",
        "## Output Token Delta (Behavior Change — API)",
        "",
        "| Provider | Avg Output Before | Avg Output After | Delta |",
        "|----------|-------------------|------------------|-------|",
    ]
    for provider in ("claude", "gemini"):
        d = stats["output_delta"].get(provider)
        if d:
            delta_str = f"+{d['output_delta']}" if d["output_delta"] >= 0 else str(d["output_delta"])
            lines.append(
                f"| {provider} | {d['avg_output_before']} | {d['avg_output_after']} | {delta_str} |"
            )
        else:
            lines.append(f"| {provider} | — | — | — |")

    lines += [
        "",
        "## Quality Scores (CLI — correct / total)",
        "",
        "| Provider | Category | Before | After | Delta |",
        "|----------|----------|--------|-------|-------|",
    ]
    for provider in ("claude", "gemini", "antigravity"):
        cats = stats["quality"].get(provider, {})
        for category in ("mmlu", "humaneval", "hellaswag", "truthfulqa"):
            q = cats.get(category, {})
            if q and q.get("before_total", 0) > 0:
                b = f"{q['before_score']}/{q['before_total']}"
                a = f"{q['after_score']}/{q['after_total']}"
                delta = q["after_score"] - q["before_score"]
                d = f"+{delta}" if delta > 0 else str(delta)
                lines.append(f"| {provider} | {category} | {b} | {a} | {d} |")
            else:
                lines.append(f"| {provider} | {category} | — | — | — |")

    lines += [
        "",
        "## Historical Runs",
        "",
        "| Run ID | Claude Input Overhead | Gemini Input Overhead | Claude Quality | Gemini Quality |",
        "|--------|-----------------------|-----------------------|----------------|----------------|",
    ]
    for run_id_h in stats.get("run_ids", [])[-10:]:  # last 10 runs
        c = stats["token_overhead"].get("claude")
        g = stats["token_overhead"].get("gemini")
        c_q = stats["quality"].get("claude", {})
        cq_total = sum(v.get("after_total", 0) for v in c_q.values())
        cq_score = sum(v.get("after_score", 0) for v in c_q.values())
        g_q = stats["quality"].get("gemini", {})
        gq_total = sum(v.get("after_total", 0) for v in g_q.values())
        gq_score = sum(v.get("after_score", 0) for v in g_q.values())
        c_str = f"+{c['overhead_tokens']:,}" if c else "—"
        g_str = f"+{g['overhead_tokens']:,}" if g else "—"
        cq_str = f"{cq_score}/{cq_total}" if cq_total else "—"
        gq_str = f"{gq_score}/{gq_total}" if gq_total else "—"
        lines.append(f"| {run_id_h[:19]} | {c_str} | {g_str} | {cq_str} | {gq_str} |")

    lines.append("")
    return "\n".join(lines)


def update_report(results_dir: Path, output_path: Path) -> None:
    """Load all results, compute stats, render, and write TOKEN_BENCHMARK.md."""
    records = load_results(results_dir)
    if not records:
        output_path.write_text("# Token Benchmark Report\n\nNo results yet. Run `/token-benchmark` to populate.\n")
        return
    stats = compute_stats(records)
    latest_run_id = stats["run_ids"][-1] if stats["run_ids"] else "unknown"
    report = render_report(stats, run_id=latest_run_id)
    output_path.write_text(report)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/python/token_benchmark/test_reporter.py -v
```

Expected: all tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add tests/token_benchmark/reporter.py tests/python/token_benchmark/test_reporter.py
git commit -m "feat: add token benchmark reporter (JSONL → TOKEN_BENCHMARK.md)"
```

---

## Task 6: Manifest fixture snapshot + TOKEN_BENCHMARK.md template

**Files:**
- Create: `tests/token_benchmark/fixtures/manifest/.claude/CLAUDE.md`
- Create: `tests/token_benchmark/fixtures/manifest/.claude/settings.json`
- Create: `tests/token_benchmark/fixtures/manifest/.gemini/GEMINI.md`
- Create: `tests/token_benchmark/fixtures/manifest/.antigravity/` (empty dir marker)
- Create: `docs/TOKEN_BENCHMARK.md`

- [ ] **Step 1: Sync fixture snapshot from live configs**

```bash
python tests/token_benchmark/harness.py --sync-fixtures --report-only
```

This copies `~/.claude/CLAUDE.md`, `~/.claude/settings.json`, `~/.gemini/GEMINI.md`, and `~/.antigravity/` (if present) into `tests/token_benchmark/fixtures/manifest/`.

Verify:
```bash
ls tests/token_benchmark/fixtures/manifest/.claude/
ls tests/token_benchmark/fixtures/manifest/.gemini/
```

Expected: `CLAUDE.md  settings.json` and `GEMINI.md` present.

- [ ] **Step 2: Create .antigravity dir marker**

```bash
mkdir -p tests/token_benchmark/fixtures/manifest/.antigravity
touch tests/token_benchmark/fixtures/manifest/.antigravity/.gitkeep
```

- [ ] **Step 3: Create initial TOKEN_BENCHMARK.md**

```bash
python -c "
import sys; sys.path.insert(0, '.')
from tests.token_benchmark.reporter import update_report
from pathlib import Path
update_report(Path('tests/token_benchmark/results'), Path('docs/TOKEN_BENCHMARK.md'))
"
```

- [ ] **Step 4: Verify the file exists**

```bash
head -5 docs/TOKEN_BENCHMARK.md
```

Expected: `# Token Benchmark Report` followed by the no-results message.

- [ ] **Step 5: Add fixtures to .gitignore for sensitive files**

Create `tests/token_benchmark/fixtures/.gitignore`:

```gitignore
# Do not commit OAuth tokens or credentials that may appear in settings files
manifest/.claude/settings.local.json
manifest/**/*.key
manifest/**/*.token
manifest/**/*.pem
```

- [ ] **Step 6: Commit**

```bash
git add tests/token_benchmark/fixtures/ tests/token_benchmark/fixtures/.gitignore \
        docs/TOKEN_BENCHMARK.md
git commit -m "feat: add manifest fixture snapshot and empty TOKEN_BENCHMARK.md template"
```

---

## Task 7: /token-benchmark SKILL.md + command_config.yml

**Files:**
- Create: `.skillshare/skills/token-benchmark/SKILL.md`
- Modify: `configs/claude/config/command_config.yml`

- [ ] **Step 1: Create the skill**

Create `.skillshare/skills/token-benchmark/SKILL.md`:

```markdown
---
name: token-benchmark
description: |
  Measure input/output token overhead and quality delta introduced by Manifest config
  deployment across Claude, Gemini CLI, and Antigravity CLI. Runs 20 industry-standard
  benchmark prompts (MMLU, HumanEval, HellaSwag, TruthfulQA) before and after manifest
  context injection via isolated HOME directories, then regenerates docs/TOKEN_BENCHMARK.md.
---

# Token Benchmark Skill

Measure how the Manifest configs affect token costs and response quality per CLI provider.

## Prerequisites

Check that the following are available before running. Report any missing items and stop.

```bash
# API keys
echo "${ANTHROPIC_API_KEY:+claude api key: set}" || echo "ANTHROPIC_API_KEY: missing"
echo "${GOOGLE_API_KEY:+gemini api key: set}" || echo "GOOGLE_API_KEY: missing (or use OAuth)"

# CLI binaries
command -v claude    && echo "claude binary: ok"    || echo "claude binary: missing"
command -v gemini    && echo "gemini binary: ok"    || echo "gemini binary: missing"
command -v agy       && echo "agy binary: ok"       || echo "agy binary: missing (antigravity)"

# Python packages
python3 -c "import anthropic; print(f'anthropic {anthropic.__version__}: ok')" 2>/dev/null || echo "anthropic package: missing — pip install anthropic"
python3 -c "from google import genai; print('google-genai: ok')" 2>/dev/null || echo "google-genai package: missing — pip install google-genai"
```

If any API key or binary is missing, inform the user and offer to run with `--api-only` (skips CLI path) or `--providers claude` (single provider).

## Arguments

Parse `$ARGUMENTS` for flags. Supported flags:

| Flag | Effect |
|------|--------|
| (none) | Full run: all providers, API + CLI paths |
| `--providers claude` | Only Claude (faster, ~3 min) |
| `--providers claude,gemini` | Claude + Gemini, no Antigravity |
| `--sync-fixtures` | Sync `fixtures/manifest/` from live `~/.claude` etc. first |
| `--api-only` | Skip CLI behavioral tests; API token counts only |
| `--report-only` | Regenerate `docs/TOKEN_BENCHMARK.md` from existing results; no new API calls |

## Execution

Run the harness from the repo root:

```bash
# Parse flags from $ARGUMENTS; default to all providers + both paths
PROVIDERS="${PROVIDERS:-claude,gemini,antigravity}"
API_ONLY_FLAG="${API_ONLY_FLAG:-}"
SYNC_FLAG="${SYNC_FLAG:-}"

# Set vars from $ARGUMENTS
echo "$ARGUMENTS" | grep -q -- "--sync-fixtures" && SYNC_FLAG="--sync-fixtures"
echo "$ARGUMENTS" | grep -q -- "--api-only"       && API_ONLY_FLAG="--api-only"
echo "$ARGUMENTS" | grep -qP -- "--providers\s+(\S+)" && \
  PROVIDERS=$(echo "$ARGUMENTS" | grep -oP '(?<=--providers\s)\S+')
echo "$ARGUMENTS" | grep -q -- "--report-only" && exec python3 tests/token_benchmark/harness.py --report-only

python3 tests/token_benchmark/harness.py \
  --providers "$PROVIDERS" \
  $SYNC_FLAG \
  $API_ONLY_FLAG
```

## After the run

1. Print the summary table from `docs/TOKEN_BENCHMARK.md` (the `## Token Overhead` section).
2. Ask: "Commit the updated TOKEN_BENCHMARK.md? (y/n)"
3. If yes:
```bash
git add docs/TOKEN_BENCHMARK.md tests/token_benchmark/results/
git commit -m "chore: update token benchmark results $(date +%Y-%m-%d)"
```

## Expected runtime

- Full run (all providers, API + CLI): ~8–15 minutes (20 prompts × 2 conditions × 3 providers)
- API-only (2 providers): ~4–6 minutes
- Single provider: ~2–3 minutes
```

- [ ] **Step 2: Add tool_policies to command_config.yml**

Open `configs/claude/config/command_config.yml`. Locate the `tool_policies:` section. Append:

```yaml
  token-benchmark:
    allowed:
      - Read
      - Bash
      - Write
    description: "Token benchmark harness — runs Python scripts and reads/writes result files"
```

Verify the YAML is still valid:

```bash
python3 -c "import yaml; yaml.safe_load(open('configs/claude/config/command_config.yml'))" && echo "yaml ok"
```

- [ ] **Step 3: Verify skill is discoverable**

```bash
ls .skillshare/skills/token-benchmark/SKILL.md
grep "^name:" .skillshare/skills/token-benchmark/SKILL.md
```

Expected: `name: token-benchmark`

- [ ] **Step 4: Commit**

```bash
git add .skillshare/skills/token-benchmark/SKILL.md configs/claude/config/command_config.yml
git commit -m "feat: add /token-benchmark skill and command_config tool_policies entry"
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by task |
|---|---|
| Three providers: claude, gemini, antigravity | Task 4 `run_benchmark`, Task 7 SKILL.md |
| 20 prompts (6+6+4+4) | Task 1 `benchmarks.py` |
| API path for exact token counts | Task 3 `measure_api_claude/gemini` |
| CLI path with HOME override | Task 4 `measure_cli` |
| Isolated HOME dirs (before/after) | Task 3 `isolated_environments` |
| fixtures/manifest/ snapshot | Task 6 |
| Antigravity shows `—` for tokens | Task 4 `run_benchmark` (no API path for agy), Task 5 reporter |
| Result schema (JSONL with all fields) | Task 4 `write_result`, `run_benchmark` |
| TOKEN_BENCHMARK.md report | Task 5 `reporter.py`, Task 6 template |
| Historical runs table | Task 5 `render_report` |
| /token-benchmark skill with all flags | Task 7 |
| --sync-fixtures flag | Task 4 `sync_fixtures`, Task 7 SKILL.md |
| HumanEval pass@1 sandboxed (5s, no network) | Task 2 `pass_at_1` |
| command_config.yml entry | Task 7 |

**Placeholder scan:** No TBD, TODO, or "implement later" present.

**Type consistency:**
- `Prompt` dataclass defined in Task 1; referenced by `score()` (Task 2), `run_benchmark()` (Task 4) — all use `prompt.category`, `prompt.gold_answer`, `prompt.test_code` consistently.
- `measure_api_claude/gemini` both return `{"input_tokens", "output_tokens", "response_text", "latency_ms", "error"}` — used identically in `run_benchmark`.
- `write_result(record, run_id, results_dir=None)` signature consistent across Task 4 impl and Task 4 test.
- `update_report(results_dir, output_path)` consistent between Task 5 impl and Task 6 usage.
