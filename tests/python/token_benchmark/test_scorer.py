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
        assert pass_at_1("return a +* b", p) == 0

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
        assert score(p.gold_answer, p) == 1

    def test_dispatches_hellaswag(self):
        p = next(b for b in BENCHMARKS if b.category == "hellaswag")
        assert score(p.gold_answer, p) == 1

    def test_dispatches_truthfulqa(self):
        p = next(b for b in BENCHMARKS if b.category == "truthfulqa")
        assert score(p.gold_answer, p) == 1

    def test_dispatches_humaneval(self):
        p = next(b for b in BENCHMARKS if b.prompt_id == "humaneval_001")
        assert score("return a + b", p) == 1
