"""Tests for benchmark prompt fixtures."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from tests.token_benchmark.benchmarks import BENCHMARKS, PROVIDER_CLI_CONFIG


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
                assert b.gold_answer in ("A", "B", "C", "D"), (
                    f"{b.prompt_id}: {b.gold_answer!r}"
                )

    def test_hellaswag_gold_answers_are_digits(self):
        for b in BENCHMARKS:
            if b.category == "hellaswag":
                assert b.gold_answer in ("0", "1", "2", "3"), (
                    f"{b.prompt_id}: {b.gold_answer!r}"
                )

    def test_truthfulqa_gold_answers_are_bool(self):
        for b in BENCHMARKS:
            if b.category == "truthfulqa":
                assert b.gold_answer in ("True", "False"), (
                    f"{b.prompt_id}: {b.gold_answer!r}"
                )

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
            assert cfg["binary"], f"{provider} binary is empty"
            assert "flags" in cfg, f"{provider} missing flags"
