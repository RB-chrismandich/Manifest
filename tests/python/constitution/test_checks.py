"""Check behavior, and — more importantly — the false positives each check must not raise.

Every "does not flag" case here was an observed false positive in the survey of
this repo's 138 Python files. Deleting one of those tests re-opens the defect it
pins, so each carries the reason inline.
"""

import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "configs" / "claude" / "scripts"))

from constitution import registry, source
from constitution.checks import run_checks

REG = registry.load()


def analyze(tmp_path, code, name="mod.py", checks=None):
    path = tmp_path / name
    path.write_text(textwrap.dedent(code).lstrip("\n"), encoding="utf-8")
    src = source.SourceFile.load(path, REG)
    return run_checks(src, only=checks)


def ids(findings):
    return sorted(f.check for f in findings)


# --------------------------------------------------------------------------
# C-DATA — embedded payloads
# --------------------------------------------------------------------------


def test_flags_embedded_json_string(tmp_path):
    payload = "\n".join(f'    "key{i}": "value{i}",' for i in range(12))
    findings = analyze(
        tmp_path,
        f'CONFIG = """\n{{\n{payload}\n}}\n"""\n',
        checks=["C-DATA"],
    )
    assert ids(findings) == ["C-DATA"]
    assert "CONFIG" in findings[0].message


def test_does_not_flag_module_docstring_that_reads_like_yaml(tmp_path):
    """generate_cursor_agents.py has a 45-line docstring a regex would misread."""
    body = "\n".join(f"key{i}: value{i}" for i in range(20))
    findings = analyze(
        tmp_path, f'"""Module.\n\n{body}\n"""\n\nX = 1\n', checks=["C-DATA"]
    )
    assert findings == []


def test_does_not_flag_docstring_of_function_or_class(tmp_path):
    # Indentation is built explicitly: a dedent-based fixture here would produce
    # unparseable source, and an unparseable file yields no findings for the
    # wrong reason — the test would pass while checking nothing.
    body = "\n".join(f"    field{i}: description {i}" for i in range(20))
    code = f'class Thing:\n    """Docs.\n\n{body}\n    """\n\n\ndef go():\n    """Docs.\n\n{body}\n    """\n'
    assert analyze(tmp_path, code, checks=["C-DATA"]) == []


def test_does_not_flag_runtime_computed_dict(tmp_path):
    """opus_attribution_report.py builds report dicts whose values are calls."""
    rows = "\n".join(f'    "k{i}": compute(root, {i}),' for i in range(20))
    findings = analyze(
        tmp_path,
        f"def build(root):\n    return {{\n{rows}\n    }}\n",
        checks=["C-DATA"],
    )
    assert findings == []


def test_flags_all_literal_module_level_dict(tmp_path):
    """agents/config.py::_default_config() is 155 lines of pure literal data."""
    rows = "\n".join(f'    "k{i}": "v{i}",' for i in range(20))
    findings = analyze(tmp_path, f"DEFAULTS = {{\n{rows}\n}}\n", checks=["C-DATA"])
    assert ids(findings) == ["C-DATA"]


def test_exemption_comment_with_reason_suppresses(tmp_path):
    rows = "\n".join(f'    "k{i}": "v{i}",' for i in range(20))
    code = f"# constitution: exempt C-DATA — bootstrap default, config not loadable yet\nDEFAULTS = {{\n{rows}\n}}\n"
    assert analyze(tmp_path, code, checks=["C-DATA"]) == []


def test_exemption_without_reason_is_itself_a_finding(tmp_path):
    """A bare exempt is how a rule quietly dies; it must cost something."""
    rows = "\n".join(f'    "k{i}": "v{i}",' for i in range(20))
    code = f"# constitution: exempt C-DATA\nDEFAULTS = {{\n{rows}\n}}\n"
    findings = analyze(tmp_path, code, checks=["C-DATA"])
    assert len(findings) == 1
    assert "reason" in findings[0].message.lower()


def test_severity_tiers_by_span_length(tmp_path):
    def span(n):
        rows = "\n".join(f'    "k{i}": "v{i}",' for i in range(n))
        return analyze(tmp_path, f"D = {{\n{rows}\n}}\n", checks=["C-DATA"])[0].severity

    assert span(20) == "info"
    assert span(50) == "warn"
    assert span(90) == "error"


def test_high_interpolation_string_is_reported_as_template(tmp_path):
    """cli_wrapper.py's BASH_TEMPLATE is a template, not a data payload."""
    lines = "\n".join(f"line {i} {{slot{i}}}" for i in range(20))
    findings = analyze(tmp_path, f'TEMPLATE = """\n{lines}\n"""\n', checks=["C-DATA"])
    assert len(findings) == 1
    assert "template" in findings[0].message.lower()


def test_sql_adjacent_to_execute_is_not_a_payload(tmp_path):
    columns = "\n".join(f"    col{i}," for i in range(12))
    code = f'def q(cur):\n    cur.execute("""\n    SELECT\n{columns}\n    id\n    FROM t\n    """)\n'
    assert analyze(tmp_path, code, checks=["C-DATA"]) == []


# --------------------------------------------------------------------------
# C-SIZE — ceilings
# --------------------------------------------------------------------------


def test_flags_file_over_ceiling(tmp_path):
    code = "\n".join(f"x{i} = {i}" for i in range(600))
    findings = analyze(tmp_path, code + "\n", checks=["C-SIZE"])
    assert any("file" in f.message for f in findings)


def test_flags_long_function_and_deep_nesting(tmp_path):
    body = "\n".join(f"    y{i} = {i}" for i in range(80))
    findings = analyze(tmp_path, f"def big():\n{body}\n", checks=["C-SIZE"])
    assert any("function" in f.message for f in findings)


def test_flags_god_class_by_method_count(tmp_path):
    methods = "\n".join(f"    def m{i}(self):\n        return {i}\n" for i in range(15))
    findings = analyze(tmp_path, f"class God:\n{methods}", checks=["C-SIZE"])
    assert any("method" in f.message for f in findings)


def test_flags_too_many_parameters(tmp_path):
    findings = analyze(
        tmp_path, "def f(a, b, c, d, e, g, h):\n    return a\n", checks=["C-SIZE"]
    )
    assert any("parameter" in f.message for f in findings)


def test_self_and_cls_do_not_count_toward_parameters(tmp_path):
    code = "class C:\n    def f(self, a, b, c, d, e):\n        return a\n"
    findings = analyze(tmp_path, code, checks=["C-SIZE"])
    assert not any("parameter" in f.message for f in findings)


def test_small_file_is_clean(tmp_path):
    assert (
        analyze(tmp_path, "def f(a: int) -> int:\n    return a\n", checks=["C-SIZE"])
        == []
    )


# --------------------------------------------------------------------------
# C-DUPE — duplication
# --------------------------------------------------------------------------


def test_flags_repeated_block(tmp_path):
    block = "\n".join(f"    step{i}()" for i in range(10))
    code = f"def a():\n{block}\n\n\ndef b():\n{block}\n"
    findings = analyze(tmp_path, code, checks=["C-DUPE"])
    assert ids(findings) == ["C-DUPE"]


def test_duplication_survives_whitespace_and_comment_differences(tmp_path):
    first = "\n".join(f"    step{i}()" for i in range(10))
    second = "\n".join(f"    step{i}()  # note {i}" for i in range(10))
    code = f"def a():\n{first}\n\n\ndef b():\n{second}\n"
    assert ids(analyze(tmp_path, code, checks=["C-DUPE"])) == ["C-DUPE"]


def test_short_repeats_are_not_duplication(tmp_path):
    code = "def a():\n    x()\n    y()\n\n\ndef b():\n    x()\n    y()\n"
    assert analyze(tmp_path, code, checks=["C-DUPE"]) == []


def test_repeated_import_and_boilerplate_lines_are_not_duplication(tmp_path):
    """Structural lines repeat by nature; flagging them makes the check useless."""
    code = (
        "def a():\n"
        + "\n".join(["    pass"] * 12)
        + "\n\n\ndef b():\n"
        + "\n".join(["    pass"] * 12)
        + "\n"
    )
    assert analyze(tmp_path, code, checks=["C-DUPE"]) == []


# --------------------------------------------------------------------------
# C-ERR — error handling
# --------------------------------------------------------------------------


def test_flags_bare_except(tmp_path):
    # Asserts on the message, not just the check id: with `except: pass` the
    # swallow rule also fires, so an id-only assertion passes even when
    # bare-except detection is deleted outright (caught by mutation).
    code = "def f():\n    try:\n        g()\n    except:\n        pass\n"
    findings = analyze(tmp_path, code, checks=["C-ERR"])
    assert any("bare" in f.message for f in findings)


def test_flags_swallowed_exception(tmp_path):
    code = "def f():\n    try:\n        g()\n    except ValueError:\n        pass\n"
    findings = analyze(tmp_path, code, checks=["C-ERR"])
    assert any("swallow" in f.message.lower() for f in findings)


def test_flags_log_and_drop(tmp_path):
    code = "def f():\n    try:\n        g()\n    except ValueError:\n        logger.exception('boom')\n"
    findings = analyze(tmp_path, code, checks=["C-ERR"])
    assert any(
        "swallow" in f.message.lower() or "drop" in f.message.lower() for f in findings
    )


def test_flags_reraise_that_discards_cause(tmp_path):
    code = "def f():\n    try:\n        g()\n    except ValueError as err:\n        raise RuntimeError('x')\n"
    findings = analyze(tmp_path, code, checks=["C-ERR"])
    assert any("cause" in f.message.lower() for f in findings)


def test_accepts_narrow_catch_with_context_and_cause(tmp_path):
    code = (
        "def f(p):\n"
        "    try:\n"
        "        g(p)\n"
        "    except ValueError as err:\n"
        "        raise RuntimeError(f'bad {p}') from err\n"
    )
    assert analyze(tmp_path, code, checks=["C-ERR"]) == []


def test_accepts_documented_fail_open(tmp_path):
    """A hook that must never break its tool is the sanctioned fail-open case."""
    code = (
        "def f():\n"
        "    try:\n"
        "        g()\n"
        "    # constitution: exempt C-ERR — hook must never break the tool it wraps\n"
        "    except Exception:\n"
        "        return None\n"
    )
    assert analyze(tmp_path, code, checks=["C-ERR"]) == []


def test_accepts_reraise_of_the_same_error(tmp_path):
    code = "def f():\n    try:\n        g()\n    except ValueError:\n        cleanup()\n        raise\n"
    assert analyze(tmp_path, code, checks=["C-ERR"]) == []


# --------------------------------------------------------------------------
# Cross-language: non-Python files get the line-based subset, not silence
# --------------------------------------------------------------------------


def test_shell_heredoc_payload_is_flagged(tmp_path):
    body = "\n".join(f"key{i}: value{i}" for i in range(20))
    code = f"#!/usr/bin/env bash\ncat << 'EOF' > out.yml\n{body}\nEOF\n"
    findings = analyze(tmp_path, code, name="run.sh", checks=["C-DATA"])
    assert ids(findings) == ["C-DATA"]


def test_shell_usage_heredoc_is_exempt(tmp_path):
    """The repo mandates --help text as a heredoc; flagging it would be absurd."""
    body = "\n".join(f"  --flag{i}   does thing {i}" for i in range(20))
    code = f"#!/usr/bin/env bash\nusage() {{\ncat << 'USAGE'\n{body}\nUSAGE\n}}\n"
    assert analyze(tmp_path, code, name="run.sh", checks=["C-DATA"]) == []


def test_shell_embedded_python_heredoc_is_not_a_data_payload(tmp_path):
    body = "\n".join(f"print({i})" for i in range(20))
    code = f"#!/usr/bin/env bash\npython3 - << 'PY'\n{body}\nPY\n"
    assert analyze(tmp_path, code, name="run.sh", checks=["C-DATA"]) == []


def test_unknown_language_yields_no_findings(tmp_path):
    assert analyze(tmp_path, "# hello\n" * 900, name="notes.md") == []
