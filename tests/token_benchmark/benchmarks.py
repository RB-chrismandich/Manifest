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
