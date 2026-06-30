"""Quality scoring for token benchmark results."""

import os
import re
import subprocess
import tempfile


def exact_match_letter(response: str, gold: str) -> int:
    """Score MMLU (A-D) and HellaSwag (0-3).

    Checks the start of the response first (model followed instructions) before
    falling back to the first standalone match — reduces false hits from numbers
    in explanatory text like "2 of the 3 options suggest...".
    """
    text = response.strip()
    # Priority: answer at the start of the response
    m = re.match(r"^([A-Da-d]|[0-3])\b", text)
    if m:
        return 1 if m.group(1).upper() == gold.upper() else 0
    # Fallback: first standalone letter/digit in response
    m = re.search(r"\b([A-Da-d]|[0-3])\b", text)
    if not m:
        return 0
    return 1 if m.group(1).upper() == gold.upper() else 0


def exact_match_bool(response: str, gold: str) -> int:
    """Score TruthfulQA by finding first True/False in response."""
    text = response.lower().strip()
    ti_match = re.search(r"\btrue\b", text)
    fi_match = re.search(r"\bfalse\b", text)
    ti = ti_match.start() if ti_match else -1
    fi = fi_match.start() if fi_match else -1
    if ti == -1 and fi == -1:
        return 0
    answer = "True" if fi == -1 or (ti != -1 and ti < fi) else "False"
    return 1 if answer == gold else 0


def pass_at_1(response: str, prompt) -> int:
    """Score HumanEval pass@1 by executing extracted code in a subprocess (5s timeout).

    Credentials are stripped from the subprocess environment to prevent leakage
    of API keys or tokens present in the caller's environment. No OS-level
    network or filesystem isolation is applied — this is a local dev tool.
    """
    code = _extract_code(response)
    if not code.strip():
        return 0

    # If response includes full function def, use it directly
    if re.search(r"def \w+\s*\(", code):
        full_code = code + "\n\n" + prompt.test_code
    else:
        # Response is just the body — prepend signature from prompt
        func_sig = _extract_func_sig(prompt.text)
        lines = code.strip().splitlines()
        body = "\n".join(("    " + line) if line.strip() else "" for line in lines)
        if not body:
            return 0
        full_code = func_sig + "\n" + body + "\n\n" + prompt.test_code

    try:
        result = subprocess.run(
            ["python3", "-c", full_code],
            capture_output=True,
            text=True,
            timeout=5,
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin")},
            cwd=tempfile.gettempdir(),
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
    m = re.search(r"```(?:python)?\s*\n(.*?)\n\s*```", response, re.DOTALL)
    return m.group(1) if m else response


def _extract_func_sig(prompt_text: str) -> str:
    """Extract the def ... : line from a HumanEval prompt."""
    m = re.search(r"(def \w+\(.*?\)\s*(?:->[^:]+)?:)", prompt_text, re.DOTALL)
    return m.group(1) if m else "def func():"
